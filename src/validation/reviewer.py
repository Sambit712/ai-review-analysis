"""
Human-in-the-Loop Review Console and QA Manager.
Allows researchers to inspect flagged low-confidence classifications, override labels, and approve them.
"""

from typing import List, Dict, Any, Optional
from ..storage.db import FeedbackDatabase


class HumanReviewManager:
    """Manages Human-in-the-Loop review queue and overrides in DuckDB."""

    def __init__(self, db: Optional[FeedbackDatabase] = None):
        self.db = db or FeedbackDatabase()

    def get_review_queue(self, min_confidence_threshold: float = 0.70, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch records with low confidence score or in review status."""
        conn = self.db.get_connection()
        try:
            query = f"""
                SELECT r.record_id, r.product_category, r.raw_text, r.source,
                       b.wishlist_intent, b.purchase_blocker, b.information_gap,
                       b.theme, b.confidence_score, b.verbatim_evidence, b.status
                FROM raw_feedback r
                JOIN behavioral_records b ON r.record_id = b.record_id
                WHERE b.confidence_score < {min_confidence_threshold} OR b.status = 'REVIEW_REQUIRED'
                ORDER BY b.confidence_score ASC
                LIMIT {limit};
            """
            df = conn.execute(query).fetchdf()
            records = df.to_dict(orient="records")
            for r in records:
                if r.get("purchase_blocker") is not None:
                    r["purchase_blocker"] = [str(x) for x in r["purchase_blocker"]]
                if r.get("information_gap") is not None:
                    r["information_gap"] = [str(x) for x in r["information_gap"]]
            return records
        finally:
            conn.close()

    def approve_or_override_classification(
        self,
        record_id: str,
        theme: Optional[str] = None,
        wishlist_intent: Optional[str] = None,
        purchase_blocker: Optional[List[str]] = None,
        information_gap: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> bool:
        """Apply human expert approval or override to a record."""
        conn = self.db.get_connection()
        try:
            updates = ["status = 'HUMAN_APPROVED'", "confidence_score = 1.0"]
            params = []

            if theme:
                updates.append("theme = ?")
                params.append(theme)
            if wishlist_intent:
                updates.append("wishlist_intent = ?")
                params.append(wishlist_intent)
            if purchase_blocker:
                updates.append("purchase_blocker = ?")
                params.append(purchase_blocker)
            if information_gap:
                updates.append("information_gap = ?")
                params.append(information_gap)

            params.append(record_id)
            update_sql = f"""
                UPDATE behavioral_records
                SET {', '.join(updates)}
                WHERE record_id = ?;
            """
            conn.execute(update_sql, params)
            return True
        finally:
            conn.close()
