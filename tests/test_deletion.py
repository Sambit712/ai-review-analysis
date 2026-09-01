"""
Automated tests for review deletion functionality across Database, Pipeline, and API layers.
"""

import os
import pytest
from fastapi.testclient import TestClient

from src.storage.db import FeedbackDatabase
from src.pipeline.incremental import IncrementalPipeline
from src.ai.classifier import BehavioralClassifier
from src.api.main import app


SAMPLE_RECORDS = [
    {
        "record_id": "DEL_REC_001",
        "source": "NYKAA",
        "source_url": "https://nykaa.com/reviews/1",
        "date": "2026-08-01",
        "text": "Great shade for medium skin, love the finish.",
        "product_category": "FOUNDATION",
    },
    {
        "record_id": "DEL_REC_002",
        "source": "AMAZON",
        "source_url": "https://amazon.in/reviews/2",
        "date": "2026-08-02",
        "text": "The shade oxidized and turned orange after 2 hours.",
        "product_category": "FOUNDATION",
    },
    {
        "record_id": "DEL_REC_003",
        "source": "REDDIT",
        "source_url": "https://reddit.com/r/beauty/3",
        "date": "2026-08-03",
        "text": "Lipstick is very drying on cracked lips.",
        "product_category": "LIPSTICK",
    },
    {
        "record_id": "DEL_REC_004",
        "source": "NYKAA",
        "source_url": "https://nykaa.com/reviews/4",
        "date": "2026-08-04",
        "text": "Beautiful lipstick nude color for daily wear.",
        "product_category": "LIPSTICK",
    },
]


@pytest.fixture
def test_db_and_pipeline(tmp_path):
    db_file = str(tmp_path / "test_del.duckdb")
    db = FeedbackDatabase(db_file)
    pipeline = IncrementalPipeline(db=db)
    pipeline.ingest_and_process(SAMPLE_RECORDS)
    return db, pipeline



def test_db_delete_by_ids(test_db_and_pipeline):
    db, _ = test_db_and_pipeline
    assert len(db.get_existing_record_ids()) == 4

    result = db.delete_records(record_ids=["DEL_REC_001", "DEL_REC_002"])
    assert result["deleted_count"] == 2
    assert set(result["deleted_ids"]) == {"DEL_REC_001", "DEL_REC_002"}

    remaining = db.get_existing_record_ids()
    assert remaining == {"DEL_REC_003", "DEL_REC_004"}

    # Verify behavioral records were also deleted
    conn = db.get_connection()
    try:
        b_count = conn.execute("SELECT COUNT(*) FROM behavioral_records WHERE record_id IN ('DEL_REC_001', 'DEL_REC_002')").fetchone()[0]
        assert b_count == 0
    finally:
        conn.close()


def test_db_delete_by_category_and_source(test_db_and_pipeline):
    db, _ = test_db_and_pipeline

    # Delete lipstick reviews from NYKAA only
    result = db.delete_records(category="LIPSTICK", source="NYKAA")
    assert result["deleted_count"] == 1
    assert result["deleted_ids"] == ["DEL_REC_004"]

    remaining = db.get_existing_record_ids()
    assert "DEL_REC_004" not in remaining
    assert "DEL_REC_003" in remaining  # Reddit lipstick remains


def test_re_ingestion_after_deletion(test_db_and_pipeline):
    db, pipeline = test_db_and_pipeline
    initial_hashes = db.get_existing_hashes()
    assert len(initial_hashes) == 4

    # Delete DEL_REC_001
    db.delete_records(record_ids=["DEL_REC_001"])
    assert len(db.get_existing_record_ids()) == 3

    # Re-ingest DEL_REC_001
    re_report = pipeline.ingest_and_process([SAMPLE_RECORDS[0]])
    assert re_report.new_records_ingested == 1
    assert re_report.duplicates_rejected == 0
    assert "DEL_REC_001" in db.get_existing_record_ids()


def test_pipeline_deletion_and_search_index_sync(test_db_and_pipeline):
    db, pipeline = test_db_and_pipeline

    # Search should find the lipstick drying review initially
    hits_before = pipeline.search_index.search("drying cracked lips", top_k=5)
    assert any(h["record_id"] == "DEL_REC_003" for h in hits_before)

    # Delete DEL_REC_003 via pipeline
    result = pipeline.delete_records(record_ids=["DEL_REC_003"], recalculate_insights=True)
    assert result["deleted_count"] == 1
    assert result["insights_recalculated"] is True

    # Search index should be updated and no longer contain DEL_REC_003
    hits_after = pipeline.search_index.search("drying cracked lips", top_k=5)
    assert not any(h["record_id"] == "DEL_REC_003" for h in hits_after)



def test_api_delete_endpoints(tmp_path, monkeypatch):
    # Set up isolated DB for FastAPI test client
    db_file = str(tmp_path / "test_api_del.duckdb")
    test_db = FeedbackDatabase(db_file)
    test_pipeline = IncrementalPipeline(db=test_db)
    test_pipeline.ingest_and_process(SAMPLE_RECORDS)


    import src.api.main as api_module
    monkeypatch.setattr(api_module, "db", test_db)
    monkeypatch.setattr(api_module, "incremental_pipeline", test_pipeline)

    client = TestClient(app)

    # 1. Single record delete
    res = client.delete("/api/records/DEL_REC_001")
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"
    assert res.json()["deleted_count"] == 1

    # 2. Deleting non-existent record returns 404
    res_404 = client.delete("/api/records/NON_EXISTENT")
    assert res_404.status_code == 404

    # 3. Bulk delete by filter
    res_bulk = client.request("DELETE", "/api/records", json={"category": "FOUNDATION"})
    assert res_bulk.status_code == 200
    assert res_bulk.json()["deleted_count"] == 1  # DEL_REC_002 was the remaining foundation

    # 4. POST /api/records/delete alias
    res_post = client.post("/api/records/delete", json={"record_ids": ["DEL_REC_003"]})
    assert res_post.status_code == 200
    assert res_post.json()["deleted_count"] == 1
