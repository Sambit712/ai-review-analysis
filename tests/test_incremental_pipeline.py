"""
Comprehensive Test Suite for Incremental Review Ingestion & AI Analysis Pipeline.
Validates:
1. Incremental Ingestion without historical reprocessing
2. Deterministic Deduplication (Stable ID + Text Hash)
3. Historical Stability (prior classifications and timestamps remain locked)
4. Aggregate Insights Recalculation (Theme frequencies, opportunity scores)
5. Traceability & Lineage
6. Failure Isolation and Retry Recovery
7. RAG Search Index Incremental Discovery
"""

import os
import json
import pytest
from src.storage.db import FeedbackDatabase
from src.pipeline.incremental import IncrementalPipeline
from src.ai.groq_client import GroqClient
from src.ai.classifier import BehavioralClassifier
from src.query.service import ResearchQueryService
from src.models.schema import ProcessingStatus


SAMPLE_BATCH_1 = [
    {
        "record_id": f"INC00{i}",
        "source": "REDDIT",
        "source_url": f"https://reddit.com/r/IndianSkincareAddicts/comments/test{i}",
        "date": "2026-08-01",
        "text": f"Saved product #{i}: {text_body}",
        "product_category": cat,
    }
    for i, (text_body, cat) in enumerate([
        ("I love this foundation shade match for warm undertones.", "FOUNDATION"),
        ("The foundation undertone is too yellow for cool olive skin.", "FOUNDATION"),
        ("Need daylight swatches of this foundation before buying.", "FOUNDATION"),
        ("Foundation shade 220 matches my mac nc35 perfectly.", "FOUNDATION"),
        ("Banana powder helps neutralize darkness on pigmented lips.", "CONCEALER"),
        ("Unsure which concealer shade will brighten without looking ashy.", "CONCEALER"),
        ("Lipstick shade Cherry Pink is too bright for wheatish complexion.", "LIPSTICK"),
        ("Looking for a peachy pink gloss that does not look frosty.", "LIPSTICK"),
        ("Waiting for shade restock of the warm honey compact.", "COMPACT"),
        ("Need swatch comparison between 220 and 230 shades.", "FOUNDATION"),
    ], 1)
]

SAMPLE_BATCH_2_MIXED = [
    # 2 Exact duplicates from Batch 1
    {
        "record_id": "INC001",
        "source": "REDDIT",
        "source_url": "https://reddit.com/r/IndianSkincareAddicts/comments/test1",
        "date": "2026-08-01",
        "text": "Saved product #1: I love this foundation shade match for warm undertones.",
        "product_category": "FOUNDATION",
    },
    {
        "record_id": "INC002",
        "source": "REDDIT",
        "source_url": "https://reddit.com/r/IndianSkincareAddicts/comments/test2",
        "date": "2026-08-01",
        "text": "Saved product #2: The foundation undertone is too yellow for cool olive skin.",
        "product_category": "FOUNDATION",
    },
    # 3 Genuinely new price/lipstick/sunscreen records
    {
        "record_id": "INC011",
        "source": "YOUTUBE",
        "source_url": "https://youtube.com/watch?v=sample11",
        "date": "2026-08-15",
        "text": "This lipstick is too expensive for me right now at Rs 1800, waiting for a festive sale discount.",
        "product_category": "LIPSTICK",
    },
    {
        "record_id": "INC012",
        "source": "YOUTUBE",
        "source_url": "https://youtube.com/watch?v=sample12",
        "date": "2026-08-15",
        "text": "Saved this matte red lipstick, waiting for Buy 2 Get 1 offer to buy with my sister.",
        "product_category": "LIPSTICK",
    },
    {
        "record_id": "INC013",
        "source": "SURVEY",
        "source_url": "https://nykaa.com/survey/2026",
        "date": "2026-08-16",
        "text": "I really want this sunscreen but worried it will leave a white cast on my wheatish complexion.",
        "product_category": "SUNSCREEN",
    },
]


def test_incremental_ingestion_and_deduplication(tmp_path):
    """
    Test that Batch 1 (10 records) is ingested and classified,
    and Batch 2 (2 duplicates + 3 new = 5 records) only processes the 3 new records.
    """
    db_path = str(tmp_path / "test_incremental.duckdb")
    db = FeedbackDatabase(db_path)
    pipeline = IncrementalPipeline(db=db)

    # Ingest Batch 1
    report1 = pipeline.ingest_and_process(SAMPLE_BATCH_1)
    assert report1.total_received == 10
    assert report1.duplicates_rejected == 0
    assert report1.new_records_ingested == 10
    assert report1.classified_count == 10
    assert report1.failed_count == 0

    stats1 = db.get_stats_summary()
    assert stats1["total_raw_records"] == 10
    assert stats1["total_analyzed_records"] == 10

    # Ingest Batch 2 (Mixed: 2 duplicates + 3 new)
    report2 = pipeline.ingest_and_process(SAMPLE_BATCH_2_MIXED)
    assert report2.total_received == 5
    assert report2.duplicates_rejected == 2
    assert report2.new_records_ingested == 3
    assert report2.classified_count == 3
    assert report2.failed_count == 0

    stats2 = db.get_stats_summary()
    assert stats2["total_raw_records"] == 13
    assert stats2["total_analyzed_records"] == 13


def test_zero_historical_reprocessing_and_stability(tmp_path):
    """
    Ensure historical records' classifications and timestamps remain locked when new records arrive.
    """
    db_path = str(tmp_path / "test_stability.duckdb")
    db = FeedbackDatabase(db_path)
    pipeline = IncrementalPipeline(db=db)

    # Batch 1
    pipeline.ingest_and_process(SAMPLE_BATCH_1)

    # Snapshot of record INC001
    info_before = db.get_record_audit_info("INC001")
    assert info_before is not None
    theme_before = info_before["theme"]
    analyzed_before = info_before["analyzed_at"]

    # Ingest Batch 2
    pipeline.ingest_and_process(SAMPLE_BATCH_2_MIXED)

    # Verify INC001 was untouched
    info_after = db.get_record_audit_info("INC001")
    assert info_after["theme"] == theme_before
    assert info_after["analyzed_at"] == analyzed_before


def test_aggregate_insights_recalculation(tmp_path):
    """
    Ensure opportunity scores and theme distributions update dynamically after incremental batch.
    """
    db_path = str(tmp_path / "test_aggregates.duckdb")
    db = FeedbackDatabase(db_path)
    pipeline = IncrementalPipeline(db=db)

    # Batch 1 (Only Shade Confidence)
    pipeline.ingest_and_process(SAMPLE_BATCH_1)

    opps1 = db.get_connection().execute("SELECT * FROM opportunity_scores WHERE opportunity_theme = 'SHADE_CONFIDENCE'").fetchdf()
    assert len(opps1) > 0
    assert opps1["frequency_count"].iloc[0] == 10
    assert opps1["frequency_pct"].iloc[0] == 100.0

    # Ingest Batch 2 (Adds Price Value and Suitability records)
    pipeline.ingest_and_process(SAMPLE_BATCH_2_MIXED)

    opps2 = db.get_connection().execute("SELECT * FROM opportunity_scores WHERE opportunity_theme = 'SHADE_CONFIDENCE'").fetchdf()
    assert opps2["frequency_count"].iloc[0] == 10
    # Total is now 13, so shade frequency percentage should be ~76.92%
    assert opps2["frequency_pct"].iloc[0] == pytest.approx(76.92, rel=1e-1)


def test_traceability_and_lineage(tmp_path):
    """
    Verify full audit lineage and traceability fields for each record.
    """
    db_path = str(tmp_path / "test_traceability.duckdb")
    db = FeedbackDatabase(db_path)
    pipeline = IncrementalPipeline(db=db)

    pipeline.ingest_and_process(SAMPLE_BATCH_2_MIXED)

    lineage = db.get_record_audit_info("INC011")
    assert lineage is not None
    assert lineage["record_id"] == "INC011"
    assert lineage["source"] == "YOUTUBE"
    assert lineage["source_url"] == "https://youtube.com/watch?v=sample11"
    assert lineage["theme"] == "PRICE_VALUE"
    assert lineage["confidence_score"] >= 0.70
    assert lineage["model_version"] is not None
    assert "Rs 1800" in lineage["raw_text"]
    assert lineage["ai_status"] in ["PROCESSED", "CLASSIFIED"]


def test_failure_recovery_and_retry(tmp_path):
    """
    Test failure containment and recovery:
    Simulate a classification failure, verify it is marked FAILED,
    and verify retry_failed_records reprocesses it successfully.
    """
    db_path = str(tmp_path / "test_failure.duckdb")
    db = FeedbackDatabase(db_path)

    fail_batch = [
        {
            "record_id": "FAIL01",
            "source": "REDDIT",
            "source_url": "https://reddit.com/r/test1",
            "date": "2026-08-01",
            "text": "Saved this foundation because I love the coverage, but cannot find my shade.",
            "product_category": "FOUNDATION",
        },
        {
            "record_id": "FAIL02",
            "source": "YOUTUBE",
            "source_url": "https://youtube.com/watch?v=test2",
            "date": "2026-08-01",
            "text": "This lipstick is too expensive for me, waiting for 50% discount.",
            "product_category": "LIPSTICK",
        },
    ]

    class MockFailingClassifier(BehavioralClassifier):
        def __init__(self):
            super().__init__()
            self.should_fail = True

        def classify_raw_dict(self, raw_record):
            if self.should_fail:
                raise RuntimeError("Simulated transient LLM API rate limit error")
            return super().classify_raw_dict(raw_record)

    failing_classifier = MockFailingClassifier()
    pipeline = IncrementalPipeline(db=db, classifier=failing_classifier)

    # Ingest 2 distinct records with failing classifier
    report = pipeline.ingest_and_process(fail_batch)
    assert report.failed_count == 2
    assert report.classified_count == 0

    # Verify raw records are safely stored with FAILED status
    failed_rows = db.get_failed_records()
    assert len(failed_rows) == 2
    assert "Simulated transient" in failed_rows[0]["error_message"]

    # Now recover: make classifier work and retry
    failing_classifier.should_fail = False
    retry_report = pipeline.retry_failed_records()
    assert retry_report.total_received == 2
    assert retry_report.classified_count == 2
    assert retry_report.failed_count == 0

    # Verify no failed records remain
    assert len(db.get_failed_records()) == 0


def test_rag_incremental_search_discovery(tmp_path):
    """
    Verify newly ingested records are immediately indexed and searchable via ResearchQueryService.
    """
    db_path = str(tmp_path / "test_rag_inc.duckdb")
    db = FeedbackDatabase(db_path)
    service = ResearchQueryService(db=db)
    pipeline = IncrementalPipeline(db=db, search_index=service.search_index)

    # Ingest Batch 1 (Foundation shade records)
    pipeline.ingest_and_process(SAMPLE_BATCH_1)

    # Search for unique phrase before batch 2 (should return 0)
    hits_before = service.search_evidence(query="festive sale discount rs 1800")
    assert len(hits_before) == 0

    # Ingest Batch 2 (Contains record INC011 with 'festive sale discount rs 1800')
    pipeline.ingest_and_process(SAMPLE_BATCH_2_MIXED)

    # Search after batch 2 (should find INC011)
    hits_after = service.search_evidence(query="festive sale discount rs 1800")
    assert len(hits_after) > 0
    assert hits_after[0]["record_id"] == "INC011"
