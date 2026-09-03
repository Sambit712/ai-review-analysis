"""
DuckDB Storage Layer for Feedback Records and AI Enrichments.
Enforces the dual-layer schema: raw immutable feedback and structured behavioral records.
"""

import os
import json
import threading
from typing import List, Optional, Dict, Any, Set
import duckdb
from ..models.schema import NormalizedFeedbackRecord, BehavioralRecord, ProcessingStatus


class FeedbackDatabase:
    """Embedded DuckDB manager for consumer feedback and AI behavioral analytics."""

    _global_lock = threading.Lock()

    def __init__(self, db_path: str = "data/raw_db/feedback.duckdb"):
        self.db_path = db_path
        self._ensure_directories()
        self.init_schema()

    def _ensure_directories(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a connection to the DuckDB instance."""
        return duckdb.connect(self.db_path)

    def init_schema(self):
        """Initialize the dual-layer relational schema."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                # 1. Raw Feedback Table (Immutable)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_feedback (
                    record_id VARCHAR PRIMARY KEY,
                    source VARCHAR NOT NULL,
                    source_url VARCHAR,
                    date VARCHAR,
                    raw_text VARCHAR NOT NULL,
                    cleaned_text VARCHAR NOT NULL,
                    product_category VARCHAR NOT NULL,
                    text_hash VARCHAR NOT NULL,
                    is_duplicate BOOLEAN DEFAULT FALSE,
                    canonical_record_id VARCHAR,
                    metadata_json VARCHAR,
                    status VARCHAR DEFAULT 'NEW',
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 2. Behavioral Records Table (AI Enrichments)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS behavioral_records (
                    record_id VARCHAR PRIMARY KEY REFERENCES raw_feedback(record_id),
                    wishlist_intent VARCHAR,
                    purchase_blocker VARCHAR[],
                    information_gap VARCHAR[],
                    comparison_behavior BOOLEAN,
                    comparison_type VARCHAR[],
                    external_research VARCHAR[],
                    decision_trigger VARCHAR[],
                    sentiment VARCHAR,
                    confidence_score DOUBLE,
                    verbatim_evidence VARCHAR,
                    theme VARCHAR,
                    segment VARCHAR,
                    status VARCHAR DEFAULT 'PROCESSED',
                    model_version VARCHAR DEFAULT 'llama-3.3-70b-versatile',
                    error_message VARCHAR,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 3. Opportunity Scoring Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunity_scores (
                    opportunity_theme VARCHAR PRIMARY KEY,
                    frequency_count INTEGER NOT NULL,
                    frequency_pct DOUBLE NOT NULL,
                    purchase_relevance_1_5 DOUBLE NOT NULL,
                    segment_impact_1_5 DOUBLE NOT NULL,
                    solvability_1_5 DOUBLE NOT NULL,
                    opportunity_score DOUBLE NOT NULL,
                    evidence_quotes VARCHAR[],
                    affected_categories VARCHAR[],
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 4. Evaluation Benchmark Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_benchmark (
                    benchmark_id VARCHAR PRIMARY KEY,
                    benchmark_name VARCHAR NOT NULL,
                    sample_size INTEGER NOT NULL,
                    overall_accuracy DOUBLE,
                    macro_f1 DOUBLE,
                    cohens_kappa DOUBLE,
                    per_theme_metrics VARCHAR,
                    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # 5. Batch Ingestion Audit Log Table
                conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_audit_log (
                    batch_id VARCHAR PRIMARY KEY,
                    total_received INTEGER NOT NULL,
                    duplicates_rejected INTEGER NOT NULL,
                    new_records_ingested INTEGER NOT NULL,
                    classified_count INTEGER NOT NULL,
                    flagged_review_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    duration_ms DOUBLE NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # Run migrations for existing tables if needed
                try:
                    conn.execute("ALTER TABLE raw_feedback ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'NEW';")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE behavioral_records ADD COLUMN IF NOT EXISTS model_version VARCHAR DEFAULT 'llama-3.3-70b-versatile';")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE behavioral_records ADD COLUMN IF NOT EXISTS error_message VARCHAR;")
                except Exception:
                    pass
            finally:
                conn.close()

    def get_existing_record_ids(self) -> Set[str]:
        """Fetch set of all existing record IDs."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                rows = conn.execute("SELECT record_id FROM raw_feedback").fetchall()
                return {r[0] for r in rows}
            finally:
                conn.close()

    def get_existing_hashes(self) -> Set[str]:
        """Fetch set of all existing content hashes for deduplication."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                rows = conn.execute("SELECT text_hash FROM raw_feedback").fetchall()
                return {r[0] for r in rows}
            finally:
                conn.close()

    def insert_normalized_records(self, records: List[NormalizedFeedbackRecord]) -> int:
        """Insert normalized records into raw_feedback."""
        if not records:
            return 0
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                count = 0
                for r in records:
                    meta_str = json.dumps(r.metadata) if r.metadata else None
                    status_val = r.status.value if hasattr(r.status, 'value') else str(r.status)
                    conn.execute("""
                    INSERT OR REPLACE INTO raw_feedback (
                        record_id, source, source_url, date, raw_text, cleaned_text,
                        product_category, text_hash, is_duplicate, canonical_record_id,
                        metadata_json, status, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, [
                        r.record_id, r.source, r.source_url, r.date, r.raw_text, r.cleaned_text,
                        r.product_category, r.text_hash, r.is_duplicate, r.canonical_record_id,
                        meta_str, status_val, r.ingested_at
                    ])
                    count += 1
                conn.execute("COMMIT;")
                return count
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def get_all_raw_records(self) -> List[Dict[str, Any]]:
        """Retrieve all raw records."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                df = conn.execute("SELECT * FROM raw_feedback ORDER BY record_id").fetchdf()
                return df.to_dict(orient="records")
            finally:
                conn.close()

    def get_unclassified_records(self) -> List[Dict[str, Any]]:
        """Fetch raw records that do not have an enriched behavioral record yet (or marked NEW)."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                query = """
                SELECT r.* FROM raw_feedback r
                LEFT JOIN behavioral_records b ON r.record_id = b.record_id
                WHERE (b.record_id IS NULL OR b.status = 'NEW') AND r.is_duplicate = FALSE
                ORDER BY r.record_id;
                """
                df = conn.execute(query).fetchdf()
                return df.to_dict(orient="records")
            finally:
                conn.close()

    def get_failed_records(self) -> List[Dict[str, Any]]:
        """Fetch records that previously failed classification and are eligible for retry."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                query = """
                SELECT r.*, b.error_message FROM raw_feedback r
                JOIN behavioral_records b ON r.record_id = b.record_id
                WHERE b.status = 'FAILED' AND r.is_duplicate = FALSE
                ORDER BY r.record_id;
                """
                df = conn.execute(query).fetchdf()
                return df.to_dict(orient="records")
            finally:
                conn.close()

    def save_behavioral_record(self, record: BehavioralRecord):
        """Save or update an enriched behavioral record."""
        self.save_behavioral_records([record])

    def save_behavioral_records(self, records: List[BehavioralRecord]):
        """Batch save enriched behavioral records."""
        if not records:
            return
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                for record in records:
                    status_val = record.status.value if hasattr(record.status, 'value') else str(record.status)
                    conn.execute("""
                    INSERT OR REPLACE INTO behavioral_records (
                        record_id, wishlist_intent, purchase_blocker, information_gap,
                        comparison_behavior, comparison_type, external_research,
                        decision_trigger, sentiment, confidence_score, verbatim_evidence,
                        theme, segment, status, model_version, error_message, analyzed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, [
                        record.record_id,
                        record.wishlist_intent.value if record.wishlist_intent else None,
                        [b.value if hasattr(b, 'value') else str(b) for b in record.purchase_blocker],
                        [g.value if hasattr(g, 'value') else str(g) for g in record.information_gap],
                        record.comparison_behavior,
                        [c.value if hasattr(c, 'value') else str(c) for c in record.comparison_type],
                        [e.value if hasattr(e, 'value') else str(e) for e in record.external_research],
                        [t.value if hasattr(t, 'value') else str(t) for t in record.decision_trigger],
                        record.sentiment.value if record.sentiment else None,
                        record.confidence_score,
                        record.verbatim_evidence,
                        record.theme,
                        record.segment,
                        status_val,
                        record.model_version or "llama-3.3-70b-versatile",
                        record.error_message,
                        record.analyzed_at,
                    ])

                    # Also update status in raw_feedback table
                    conn.execute("UPDATE raw_feedback SET status = ? WHERE record_id = ?", [status_val, record.record_id])
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def log_audit_batch(self, audit: Dict[str, Any]):
        """Log batch execution audit report."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                conn.execute("""
                INSERT OR REPLACE INTO ingestion_audit_log (
                    batch_id, total_received, duplicates_rejected, new_records_ingested,
                    classified_count, flagged_review_count, failed_count, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, [
                    audit["batch_id"],
                    audit["total_received"],
                    audit["duplicates_rejected"],
                    audit["new_records_ingested"],
                    audit["classified_count"],
                    audit["flagged_review_count"],
                    audit["failed_count"],
                    audit["duration_ms"],
                ])
            finally:
                conn.close()

    def get_audit_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent batch ingestion audit logs."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                df = conn.execute(f"SELECT * FROM ingestion_audit_log ORDER BY timestamp DESC LIMIT {limit}").fetchdf()
                return df.to_dict(orient="records")
            finally:
                conn.close()

    def get_record_audit_info(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full lineage and traceability details for a single record."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                query = """
                SELECT r.*, b.wishlist_intent, b.purchase_blocker, b.information_gap,
                       b.comparison_behavior, b.comparison_type, b.external_research,
                       b.decision_trigger, b.sentiment, b.confidence_score, b.verbatim_evidence,
                       b.theme, b.segment, b.status as ai_status, b.model_version,
                       b.error_message, b.analyzed_at
                FROM raw_feedback r
                LEFT JOIN behavioral_records b ON r.record_id = b.record_id
                WHERE r.record_id = ?;
                """
                df = conn.execute(query, [record_id]).fetchdf()
                if df.empty:
                    return None
                return df.to_dict(orient="records")[0]
            finally:
                conn.close()

    def get_stats_summary(self) -> Dict[str, Any]:
        """Get summary stats across raw feedback and behavioral records."""
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                raw_count = conn.execute("SELECT COUNT(*) FROM raw_feedback").fetchone()[0]
                canonical_count = conn.execute("SELECT COUNT(*) FROM raw_feedback WHERE is_duplicate = FALSE").fetchone()[0]
                duplicate_count = conn.execute("SELECT COUNT(*) FROM raw_feedback WHERE is_duplicate = TRUE").fetchone()[0]
                analyzed_count = conn.execute("SELECT COUNT(*) FROM behavioral_records").fetchone()[0]

                cat_df = conn.execute("SELECT product_category, COUNT(*) as cnt FROM raw_feedback GROUP BY product_category ORDER BY cnt DESC").fetchdf()
                src_df = conn.execute("SELECT source, COUNT(*) as cnt FROM raw_feedback GROUP BY source ORDER BY cnt DESC").fetchdf()

                return {
                    "total_raw_records": raw_count,
                    "total_canonical_records": canonical_count,
                    "total_duplicate_records": duplicate_count,
                    "total_analyzed_records": analyzed_count,
                    "category_breakdown": dict(zip(cat_df["product_category"], cat_df["cnt"])),
                    "source_breakdown": dict(zip(src_df["source"], src_df["cnt"])),
                }
            finally:
                conn.close()

    def delete_records(
        self,
        record_ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete a set of reviews and their associated AI behavioral records.
        Supports deleting by specific record IDs or filtering by category, source, status.
        Returns a summary dict with deleted_count and deleted_ids.
        """
        with FeedbackDatabase._global_lock:
            conn = self.get_connection()
            try:
                conditions = []
                params = []

                if record_ids:
                    placeholders = ", ".join(["?"] * len(record_ids))
                    conditions.append(f"record_id IN ({placeholders})")
                    params.extend(record_ids)

                if category and category != "ALL":
                    conditions.append("product_category = ?")
                    params.append(category)

                if source and source != "ALL":
                    conditions.append("source = ?")
                    params.append(source)

                if status and status != "ALL":
                    conditions.append("status = ?")
                    params.append(status)

                if not conditions:
                    return {"deleted_count": 0, "deleted_ids": [], "message": "No deletion criteria specified"}

                where_clause = f"WHERE {' AND '.join(conditions)}"

                # Identify which record_ids match
                id_query = f"SELECT record_id FROM raw_feedback {where_clause};"
                matching_rows = conn.execute(id_query, params).fetchall()
                target_ids = [r[0] for r in matching_rows]

                if not target_ids:
                    return {"deleted_count": 0, "deleted_ids": [], "message": "No records matched criteria"}

                id_placeholders = ", ".join(["?"] * len(target_ids))

                # 1. Delete from behavioral_records (referencing table)
                conn.execute(f"DELETE FROM behavioral_records WHERE record_id IN ({id_placeholders});", target_ids)

                # 2. Delete from raw_feedback
                conn.execute(f"DELETE FROM raw_feedback WHERE record_id IN ({id_placeholders});", target_ids)

                return {
                    "deleted_count": len(target_ids),
                    "deleted_ids": target_ids,
                    "message": f"Successfully deleted {len(target_ids)} record(s)",
                }
            finally:
                conn.close()

