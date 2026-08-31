"""
Behavioral Classifier Orchestrator.
Parses, grounds, validates, and stores enriched behavioral records in DuckDB.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import ValidationError

from ..models.schema import (
    BehavioralRecord,
    TaxonomyClassificationOutput,
    ProcessingStatus,
    Sentiment,
    WishlistIntent,
    PurchaseBlocker,
    InformationGap,
    ComparisonType,
    ExternalResearch,
    DecisionTrigger,
)
from ..storage.db import FeedbackDatabase
from ..analytics.theme_clustering import map_blocker_to_theme, THEME_TAXONOMY
from .groq_client import GroqClient
from .prompts import SYSTEM_PROMPT, format_classification_prompt


def safe_enum_cast(enum_cls, val, default=None):
    """Safely cast string to enum value."""
    if not val:
        return default
    try:
        return enum_cls(val.upper().strip())
    except (ValueError, KeyError):
        return default


def safe_enum_list(enum_cls, val_list):
    """Safely cast a list of strings to enum values."""
    if not val_list:
        return []
    res = []
    for v in val_list:
        casted = safe_enum_cast(enum_cls, v)
        if casted:
            res.append(casted)
    return res


class BehavioralClassifier:
    """Orchestrates LLM / Groq behavioral classification with strict validation."""

    def __init__(self, groq_client: Optional[GroqClient] = None, confidence_threshold: float = 0.70):
        self.client = groq_client or GroqClient()
        self.confidence_threshold = confidence_threshold

    def classify_text(self, raw_text: str, product_category: str, source: str = "FEEDBACK", record_id: str = "TEMP") -> BehavioralRecord:
        """Classify a single feedback text statement."""
        raw_dict = {
            "record_id": record_id,
            "product_category": product_category,
            "source": source,
            "raw_text": raw_text,
        }
        return self.classify_raw_dict(raw_dict)

    def classify_raw_dict(self, raw_record: Dict[str, Any]) -> BehavioralRecord:
        """Enrich a raw record dictionary into a validated BehavioralRecord."""
        rec_id = str(raw_record.get("record_id"))
        raw_text = raw_record.get("raw_text") or raw_record.get("text") or ""
        category = raw_record.get("product_category", "BEAUTY")
        source = raw_record.get("source", "FEEDBACK")

        # 1. Get structured JSON from GroqClient
        raw_json = self.client.classify_statement(text=raw_text, category=category, source=source)

        # 2. Ground truth / Verbatim quote validation
        verbatim = raw_json.get("verbatim_evidence", "")
        if verbatim and verbatim.lower() not in raw_text.lower():
            verbatim = raw_text[:120]

        # 3. Cast enums safely
        wishlist_intent = safe_enum_cast(WishlistIntent, raw_json.get("wishlist_intent"), WishlistIntent.GENUINE_PURCHASE_INTENT)
        purchase_blocker = safe_enum_list(PurchaseBlocker, raw_json.get("purchase_blocker"))
        if not purchase_blocker:
            purchase_blocker = [PurchaseBlocker.OTHER]

        information_gap = safe_enum_list(InformationGap, raw_json.get("information_gap"))
        comparison_type = safe_enum_list(ComparisonType, raw_json.get("comparison_type"))
        external_research = safe_enum_list(ExternalResearch, raw_json.get("external_research"))
        decision_trigger = safe_enum_list(DecisionTrigger, raw_json.get("decision_trigger"))
        sentiment = safe_enum_cast(Sentiment, raw_json.get("sentiment"), Sentiment.NEUTRAL)

        # 4. Deterministic theme & segment mapping
        raw_theme = str(raw_json.get("theme", "")).upper()
        if raw_theme in THEME_TAXONOMY:
            theme = raw_theme
        else:
            blocker_strs = [b.value for b in purchase_blocker]
            theme = map_blocker_to_theme(blocker_strs)

        segment = f"{category.upper()}_{theme}"

        # 5. Confidence score & review flagging
        conf = float(raw_json.get("confidence_score", 0.90))
        status = ProcessingStatus.REQUIRES_REVIEW if conf < self.confidence_threshold else ProcessingStatus.PROCESSED

        model_ver = self.client.model if hasattr(self.client, "model") else "llama-3.3-70b-versatile"

        return BehavioralRecord(
            record_id=rec_id,
            wishlist_intent=wishlist_intent,
            purchase_blocker=purchase_blocker,
            information_gap=information_gap,
            comparison_behavior=bool(raw_json.get("comparison_behavior", False)),
            comparison_type=comparison_type,
            external_research=external_research,
            decision_trigger=decision_trigger,
            sentiment=sentiment,
            confidence_score=conf,
            verbatim_evidence=verbatim or raw_text[:100],
            theme=theme,
            segment=segment,
            status=status,
            model_version=model_ver,
            analyzed_at=datetime.utcnow().isoformat(),
        )

    def process_and_save_records(
        self,
        db: FeedbackDatabase,
        limit: Optional[int] = None,
        max_workers: int = 5
    ) -> List[BehavioralRecord]:
        """
        Classify all unclassified records in DuckDB and persist results atomically.
        """
        unclassified = db.get_unclassified_records()
        if limit:
            unclassified = unclassified[:limit]

        if not unclassified:
            print("[*] No unclassified records found in database.")
            return []

        print(f"[*] Processing {len(unclassified)} records with Behavioral Classifier (Engine: {'Groq' if self.client.is_live else 'Rule-Based Fallback'})...")

        results: List[BehavioralRecord] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_rec = {executor.submit(self.classify_raw_dict, rec): rec for rec in unclassified}
            for future in as_completed(future_to_rec):
                try:
                    b_rec = future.result()
                    results.append(b_rec)
                except Exception as exc:
                    rec_id = future_to_rec[future].get("record_id")
                    print(f"[!] Error classifying record {rec_id}: {exc}")

        # Batch save to DuckDB atomically
        db.save_behavioral_records(results)

        print(f"[OK] Successfully classified and persisted {len(results)} behavioral records.")
        return results
