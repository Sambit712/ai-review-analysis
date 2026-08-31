"""
Opportunity Scoring & Prioritization Calculator.
"""

from typing import List, Dict, Any, Optional
from ..storage.db import FeedbackDatabase
from .theme_clustering import THEME_TAXONOMY


class OpportunityScorer:
    """Calculates deterministic opportunity priority scores based on empirical feedback volume."""

    def __init__(self, db: Optional[FeedbackDatabase] = None):
        self.db = db or FeedbackDatabase()

    def compute_opportunity_rankings(
        self,
        custom_weights: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Compute ranked opportunities for all behavioral themes.
        Formula: Opportunity Score = Frequency_Ratio * Relevance * Impact * Solvability * 10
        """
        conn = self.db.get_connection()
        try:
            # Query theme volume and sample quotes
            query = """
                SELECT b.theme, COUNT(*) as count,
                       list(b.verbatim_evidence)[1:3] as sample_quotes,
                       list(r.product_category)[1:3] as sample_categories
                FROM behavioral_records b
                JOIN raw_feedback r ON b.record_id = r.record_id
                GROUP BY b.theme
                ORDER BY count DESC;
            """
            df = conn.execute(query).fetchdf()
            total_records = conn.execute("SELECT COUNT(*) FROM behavioral_records").fetchone()[0] or 1

            theme_data_map = {}
            for _, row in df.iterrows():
                theme_data_map[row["theme"]] = {
                    "count": int(row["count"]),
                    "sample_quotes": row["sample_quotes"],
                    "sample_categories": row["sample_categories"],
                }

            rankings = []
            for theme_key, theme_defaults in THEME_TAXONOMY.items():
                data = theme_data_map.get(theme_key, {"count": 0, "sample_quotes": [], "sample_categories": []})
                count = data["count"]
                freq_pct = round((count / total_records) * 100, 2)
                freq_ratio = count / total_records

                override = (custom_weights or {}).get(theme_key, {})
                relevance = override.get("purchase_relevance", theme_defaults.get("default_relevance", 4.0))
                impact = override.get("segment_impact", theme_defaults.get("default_impact", 4.0))
                solvability = override.get("solvability", theme_defaults.get("default_solvability", 4.0))

                # Mathematical formula
                raw_score = freq_ratio * relevance * impact * solvability
                normalized_score = round(raw_score * 10, 2)

                quotes = data["sample_quotes"]
                clean_quotes = [str(q) for q in quotes if q is not None] if quotes is not None else []

                cats = data["sample_categories"]
                clean_cats = [str(c) for c in cats if c is not None] if cats is not None else []

                rankings.append({
                    "opportunity_theme": theme_key,
                    "name": theme_defaults.get("name", theme_key),
                    "description": theme_defaults.get("description", ""),
                    "frequency_count": count,
                    "frequency_pct": freq_pct,
                    "purchase_relevance_1_5": float(relevance),
                    "segment_impact_1_5": float(impact),
                    "solvability_1_5": float(solvability),
                    "opportunity_score": normalized_score,
                    "evidence_quotes": clean_quotes,
                    "top_categories": clean_cats,
                })

            # Sort by highest opportunity score
            rankings.sort(key=lambda x: x["opportunity_score"], reverse=True)

            # Persist to DuckDB opportunity_scores table matching exact table schema
            for item in rankings:
                conn.execute("""
                    INSERT OR REPLACE INTO opportunity_scores (
                        opportunity_theme, frequency_count, frequency_pct,
                        purchase_relevance_1_5, segment_impact_1_5, solvability_1_5,
                        opportunity_score, evidence_quotes, affected_categories
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, [
                    item["opportunity_theme"],
                    item["frequency_count"],
                    item["frequency_pct"],
                    item["purchase_relevance_1_5"],
                    item["segment_impact_1_5"],
                    item["solvability_1_5"],
                    item["opportunity_score"],
                    item["evidence_quotes"],
                    item["top_categories"],
                ])

            return rankings
        finally:
            conn.close()
