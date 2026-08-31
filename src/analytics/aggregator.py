"""
Deterministic Data Aggregation Engine for zero-hallucination metrics.
"""

from typing import Dict, List, Any, Optional
import pandas as pd
from ..storage.db import FeedbackDatabase
from .theme_clustering import THEME_TAXONOMY, map_blocker_to_theme


class AnalyticsAggregator:
    """Executes deterministic aggregation and frequency computation on DuckDB."""

    def __init__(self, db: Optional[FeedbackDatabase] = None):
        self.db = db or FeedbackDatabase()

    def get_overview_metrics(self, category: Optional[str] = None, category_filter: Optional[str] = None) -> Dict[str, Any]:
        """Compute high-level KPIs and summary counts."""
        cat = category or category_filter
        conn = self.db.get_connection()
        try:
            cat_clause = f"AND r.product_category = '{cat.upper()}'" if cat and cat != "ALL" else ""

            total_raw = conn.execute(f"SELECT COUNT(*) FROM raw_feedback r WHERE 1=1 {cat_clause}").fetchone()[0]
            total_canonical = conn.execute(f"SELECT COUNT(*) FROM raw_feedback r WHERE r.is_duplicate = FALSE {cat_clause}").fetchone()[0]
            
            analyzed_query = f"""
                SELECT COUNT(*), 
                       COALESCE(AVG(b.confidence_score), 0.0),
                       SUM(CASE WHEN b.external_research IS NOT NULL AND len(b.external_research) > 0 AND b.external_research[1] != 'NONE' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN b.comparison_behavior = TRUE THEN 1 ELSE 0 END)
                FROM behavioral_records b
                JOIN raw_feedback r ON b.record_id = r.record_id
                WHERE 1=1 {cat_clause};
            """
            row = conn.execute(analyzed_query).fetchone()
            total_analyzed = row[0] or 0
            avg_confidence = row[1] or 0.0
            ext_count = row[2] or 0
            comp_count = row[3] or 0

            ext_rate = round((ext_count / total_analyzed * 100), 1) if total_analyzed > 0 else 0.0
            comp_rate = round((comp_count / total_analyzed * 100), 1) if total_analyzed > 0 else 0.0

            total_flagged = conn.execute("SELECT COUNT(*) FROM behavioral_records WHERE status IN ('NEEDS_REVIEW', 'REQUIRES_REVIEW')").fetchone()[0]

            return {
                "total_raw_records": total_raw,
                "total_canonical_records": total_canonical,
                "total_analyzed_records": total_analyzed,
                "total_flagged_for_review": total_flagged,
                "average_confidence_score": round(float(avg_confidence), 3),
                "external_research_rate_pct": ext_rate,
                "comparison_behavior_rate_pct": comp_rate,
            }
        finally:
            conn.close()

    def get_theme_distribution(self, category: Optional[str] = None, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Compute deterministic theme frequencies."""
        cat = category or category_filter
        conn = self.db.get_connection()
        try:
            cat_clause = f"AND r.product_category = '{cat.upper()}'" if cat and cat != "ALL" else ""
            query = f"""
                SELECT b.theme, COUNT(*) as record_count
                FROM behavioral_records b
                JOIN raw_feedback r ON b.record_id = r.record_id
                WHERE 1=1 {cat_clause}
                GROUP BY b.theme
                ORDER BY record_count DESC;
            """
            df = conn.execute(query).fetchdf()
            total = df["record_count"].sum() if not df.empty else 1

            results = []
            for _, row in df.iterrows():
                theme_key = row["theme"]
                count = int(row["record_count"])
                pct = round((count / total) * 100, 2)
                theme_info = THEME_TAXONOMY.get(theme_key, {})
                results.append({
                    "theme_id": theme_key,
                    "theme_name": theme_info.get("name", theme_key.replace("_", " ").title()),
                    "name": theme_info.get("name", theme_key.replace("_", " ").title()),
                    "description": theme_info.get("description", ""),
                    "record_count": count,
                    "count": count,
                    "frequency_pct": pct,
                    "percentage": pct,
                })
            return results
        finally:
            conn.close()

    def get_blocker_frequencies(self, category: Optional[str] = None, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Calculate frequency for each purchase blocker across analyzed records."""
        cat = category or category_filter
        conn = self.db.get_connection()
        try:
            cat_filter = f"AND r.product_category = '{cat.upper()}'" if cat and cat != "ALL" else ""
            query = f"""
                SELECT blocker, COUNT(*) AS count
                FROM (
                    SELECT UNNEST(b.purchase_blocker) AS blocker
                    FROM behavioral_records b
                    JOIN raw_feedback r ON b.record_id = r.record_id
                    WHERE 1=1 {cat_filter}
                )
                GROUP BY blocker
                ORDER BY count DESC;
            """
            df = conn.execute(query).fetchdf()

            tot_query = f"""
                SELECT COUNT(*)
                FROM behavioral_records b
                JOIN raw_feedback r ON b.record_id = r.record_id
                WHERE 1=1 {cat_filter};
            """
            total_records = conn.execute(tot_query).fetchone()[0] or 1

            results = []
            for _, row in df.iterrows():
                b = str(row["blocker"]).replace("'", "").replace('"', "")
                cnt = int(row["count"])
                pct = round((cnt / total_records) * 100, 2)
                results.append({
                    "blocker": b,
                    "count": cnt,
                    "frequency_pct": pct,
                    "percentage": pct,
                    "total_analyzed_base": total_records,
                })
            return results
        finally:
            conn.close()

    # Alias for get_blocker_frequencies
    get_blocker_matrix = get_blocker_frequencies

    def get_information_gap_frequencies(self, category: Optional[str] = None, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Calculate frequency distribution for unmet information needs."""
        cat = category or category_filter
        conn = self.db.get_connection()
        try:
            cat_filter = f"AND r.product_category = '{cat.upper()}'" if cat and cat != "ALL" else ""
            query = f"""
                SELECT gap, COUNT(*) AS count
                FROM (
                    SELECT UNNEST(b.information_gap) AS gap
                    FROM behavioral_records b
                    JOIN raw_feedback r ON b.record_id = r.record_id
                    WHERE 1=1 {cat_filter}
                )
                GROUP BY gap
                ORDER BY count DESC;
            """
            df = conn.execute(query).fetchdf()
            total_records = conn.execute("SELECT COUNT(*) FROM behavioral_records").fetchone()[0] or 1

            results = []
            for _, row in df.iterrows():
                g = str(row["gap"]).replace("'", "").replace('"', "")
                cnt = int(row["count"])
                pct = round((cnt / total_records) * 100, 2)
                results.append({
                    "information_gap": g,
                    "gap": g,
                    "count": cnt,
                    "frequency_pct": pct,
                    "percentage": pct,
                })
            return results
        finally:
            conn.close()

    # Alias for get_information_gap_frequencies
    get_information_gaps = get_information_gap_frequencies

    def get_category_breakdown_matrix(self) -> Dict[str, Any]:
        """Cross-tabulate categories against primary blockers and themes."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT r.product_category, b.theme, COUNT(*) as count
                FROM behavioral_records b
                JOIN raw_feedback r ON b.record_id = r.record_id
                GROUP BY r.product_category, b.theme;
            """
            df = conn.execute(query).fetchdf()

            matrix = {}
            for _, row in df.iterrows():
                cat = row["product_category"]
                theme = row["theme"]
                cnt = int(row["count"])

                if cat not in matrix:
                    matrix[cat] = {"total": 0, "themes": {}}
                matrix[cat]["total"] += cnt
                matrix[cat]["themes"][theme] = cnt

            return matrix
        finally:
            conn.close()

    def get_channel_and_comparison_patterns(self) -> Dict[str, Any]:
        """Aggregate external research channels and comparison behavior breakdown."""
        conn = self.db.get_connection()
        try:
            # Channel breakdown
            ch_query = """
                SELECT channel, COUNT(*) as count
                FROM (
                    SELECT UNNEST(external_research) as channel
                    FROM behavioral_records
                )
                WHERE channel != 'NONE'
                GROUP BY channel
                ORDER BY count DESC;
            """
            ch_df = conn.execute(ch_query).fetchdf()

            # Comparison type breakdown
            comp_query = """
                SELECT comp_type, COUNT(*) as count
                FROM (
                    SELECT UNNEST(comparison_type) as comp_type
                    FROM behavioral_records
                )
                WHERE comp_type != 'NONE'
                GROUP BY comp_type
                ORDER BY count DESC;
            """
            comp_df = conn.execute(comp_query).fetchdf()

            return {
                "research_channels": dict(zip(ch_df["channel"], ch_df["count"])),
                "comparison_types": dict(zip(comp_df["comp_type"], comp_df["count"])),
            }
        finally:
            conn.close()

    def get_decision_triggers_distribution(self) -> List[Dict[str, Any]]:
        """Calculate frequency distribution for purchase decision triggers."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT trigger_val, COUNT(*) as count
                FROM (
                    SELECT UNNEST(decision_trigger) as trigger_val
                    FROM behavioral_records
                )
                GROUP BY trigger_val
                ORDER BY count DESC;
            """
            df = conn.execute(query).fetchdf()
            total = df["count"].sum() if not df.empty else 1

            results = []
            for _, row in df.iterrows():
                t = str(row["trigger_val"]).replace("'", "").replace('"', "")
                cnt = int(row["count"])
                pct = round((cnt / total) * 100, 2)
                results.append({
                    "trigger": t,
                    "count": cnt,
                    "percentage": pct,
                })
            return results
        finally:
            conn.close()
