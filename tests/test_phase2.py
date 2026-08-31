"""
Test suite for Phase 2: AI Behavioral Classification Layer.
"""

import pytest
from src.models.schema import (
    TaxonomyClassificationOutput,
    ProcessingStatus,
    WishlistIntent,
    PurchaseBlocker,
    InformationGap,
    ComparisonType,
    ExternalResearch,
    DecisionTrigger,
    Sentiment,
)
from src.ai.prompts import format_classification_prompt, SYSTEM_PROMPT
from src.ai.groq_client import GroqClient
from src.ai.classifier import BehavioralClassifier, safe_enum_cast, safe_enum_list
from src.storage.db import FeedbackDatabase
from src.ingestion.parsers import BatchIngestor


def test_system_prompt_contains_taxonomy():
    assert "wishlist_intent" in SYSTEM_PROMPT
    assert "purchase_blocker" in SYSTEM_PROMPT
    assert "SHADE_CONFIDENCE" in SYSTEM_PROMPT
    assert "PRICE_VALUE" in SYSTEM_PROMPT


def test_format_classification_prompt():
    prompt = format_classification_prompt(
        text="I love this foundation but cannot find my shade.",
        category="FOUNDATION",
        source="SURVEY"
    )
    assert "FOUNDATION" in prompt
    assert "I love this foundation" in prompt


def test_safe_enum_cast():
    assert safe_enum_cast(WishlistIntent, "GENUINE_PURCHASE_INTENT") == WishlistIntent.GENUINE_PURCHASE_INTENT
    assert safe_enum_cast(WishlistIntent, "non_existent_value", WishlistIntent.OTHER) == WishlistIntent.OTHER
    assert safe_enum_cast(PurchaseBlocker, "shade") == PurchaseBlocker.SHADE


def test_safe_enum_list():
    raw_blockers = ["SHADE", "PRICE_VALUE", "INVALID_BLOCKER"]
    casted = safe_enum_list(PurchaseBlocker, raw_blockers)
    assert PurchaseBlocker.SHADE in casted
    assert PurchaseBlocker.PRICE_VALUE in casted
    assert len(casted) == 2


def test_mock_classification_synthetic_statements():
    client = GroqClient()
    classifier = BehavioralClassifier(groq_client=client)

    # Foundation shade statement
    raw_foundation = {
        "record_id": "SYN002",
        "product_category": "FOUNDATION",
        "source": "SYNTHETIC_TEST",
        "raw_text": "This foundation is on my wishlist, but I'm not sure which shade matches my undertone. I want to see it on someone on YouTube.",
    }
    res = classifier.classify_raw_dict(raw_foundation)
    assert res.record_id == "SYN002"
    assert PurchaseBlocker.SHADE in res.purchase_blocker
    assert InformationGap.SHADE_CONFIDENCE in res.information_gap
    assert ExternalResearch.YOUTUBE in res.external_research
    assert res.theme == "SHADE_CONFIDENCE"
    assert res.confidence_score >= 0.70
    assert res.status in [ProcessingStatus.PROCESSED, ProcessingStatus.CLASSIFIED, "PROCESSED", "CLASSIFIED"]

    # Price concern lipstick statement
    raw_lipstick = {
        "record_id": "SYN017",
        "product_category": "FOUNDATION",
        "source": "SYNTHETIC_TEST",
        "raw_text": "This foundation is expensive for me, so I'm looking for similar coverage in a lower price range.",
    }
    res_lip = classifier.classify_raw_dict(raw_lipstick)
    assert PurchaseBlocker.PRICE_VALUE in res_lip.purchase_blocker
    assert InformationGap.PRICE_VALUE in res_lip.information_gap
    assert res_lip.theme == "PRICE_VALUE"


def test_low_confidence_flagging():
    client = GroqClient()
    classifier = BehavioralClassifier(groq_client=client, confidence_threshold=0.98)

    raw_rec = {
        "record_id": "TEST01",
        "product_category": "LIPSTICK",
        "source": "TEST",
        "raw_text": "Just looking around.",
    }
    res = classifier.classify_raw_dict(raw_rec)
    # Since confidence is ~0.95 < 0.98 threshold, it should be flagged
    assert res.status in [ProcessingStatus.REQUIRES_REVIEW, ProcessingStatus.NEEDS_REVIEW, "REQUIRES_REVIEW", "NEEDS_REVIEW", "REVIEW_REQUIRED"]


def test_e2e_classification_and_storage(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"
    db_path = str(tmp_path / "test_phase2.duckdb")

    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()

    # Ingest 35 records
    records = ingestor.ingest_file(excel_path)
    db.insert_normalized_records(records)

    # Classify all 35 records
    client = GroqClient()
    classifier = BehavioralClassifier(groq_client=client)
    classified_records = classifier.process_and_save_records(db, max_workers=4)

    assert len(classified_records) == 35

    # Verify DuckDB has 35 behavioral records
    stats = db.get_stats_summary()
    assert stats["total_analyzed_records"] == 35

    # Check unclassified records count is now 0
    unclassified_remaining = db.get_unclassified_records()
    assert len(unclassified_remaining) == 0

    # Query enriched records directly
    conn = db.get_connection()
    try:
        sample_df = conn.execute("""
            SELECT b.theme, COUNT(*) as cnt
            FROM behavioral_records b
            GROUP BY b.theme
            ORDER BY cnt DESC
        """).fetchdf()
        assert len(sample_df) > 0
        themes = sample_df["theme"].tolist()
        assert "SHADE_CONFIDENCE" in themes or "PRICE_VALUE" in themes or "SUITABILITY" in themes
    finally:
        conn.close()
