"""
Test suite for Phase 1: Ingestion, Normalization, Deduplication, and DuckDB Storage.
"""

import os
import json
import pytest
import pandas as pd
from src.models.schema import RawFeedbackRecord, NormalizedRecord
from src.ingestion.normalizer import (
    sanitize_text,
    compute_text_hash,
    normalize_category,
    normalize_source,
    normalize_raw_record,
)
from src.ingestion.deduplicator import Deduplicator
from src.ingestion.parsers import BatchIngestor
from src.storage.db import FeedbackDatabase


def test_sanitize_text():
    raw = "  “This is   a great lipstick—love it!” \n "
    cleaned = sanitize_text(raw)
    assert cleaned == '"This is a great lipstick-love it!"'


def test_normalize_category():
    assert normalize_category("Lipstick") == "LIPSTICK"
    assert normalize_category("Fashion (non-beauty)") == "FASHION"
    assert normalize_category("serum") == "SERUM"
    assert normalize_category("Lip Gloss") == "LIP_GLOSS"
    assert normalize_category(None) == "OTHER"


def test_deduplication():
    dedup = Deduplicator(fuzzy_threshold=0.85)

    rec1 = normalize_raw_record(RawFeedbackRecord(
        record_id="1", source="Reddit", text="I love this lipstick shade but the price is too high."
    ))
    rec2 = normalize_raw_record(RawFeedbackRecord(
        record_id="2", source="Reddit", text="I love this lipstick shade but the price is too high."
    ))
    rec3 = normalize_raw_record(RawFeedbackRecord(
        record_id="3", source="YouTube", text="I love this lipstick shade however the price is way too high."
    ))

    res1 = dedup.process_record(rec1)
    assert res1.is_duplicate is False
    assert res1.canonical_record_id == "1"

    # Exact duplicate
    res2 = dedup.process_record(rec2)
    assert res2.is_duplicate is True
    assert res2.canonical_record_id == "1"


def test_excel_ingestion_with_sample_dataset(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"
    assert os.path.exists(excel_path), f"Sample dataset not found at {excel_path}"

    db_path = str(tmp_path / "test_feedback.duckdb")
    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()

    records = ingestor.ingest_file(excel_path)
    assert len(records) == 35, f"Expected 35 records, got {len(records)}"

    # Check raw text preservation
    first_rec = records[0]
    assert first_rec.record_id == "1"
    assert "remember the product" in first_rec.raw_text

    # Insert into DB
    inserted = db.insert_normalized_records(records)
    assert inserted == 35

    # Check database statistics
    stats = db.get_stats_summary()
    assert stats["total_raw_records"] == 35
    assert stats["total_canonical_records"] > 0
    assert "LIPSTICK" in stats["category_breakdown"]
    assert "FOUNDATION" in stats["category_breakdown"]


def test_csv_and_json_ingestion(tmp_path):
    csv_file = str(tmp_path / "sample.csv")
    df_sample = pd.DataFrame([
        {"id": "CSV01", "comment": "Amazing serum for dry skin!", "category": "Serum", "source": "Reddit"},
        {"id": "CSV02", "comment": "Found alternative on Amazon cheaper", "category": "Lipstick", "source": "YouTube"}
    ])
    df_sample.to_csv(csv_file, index=False)

    json_file = str(tmp_path / "sample.json")
    json_data = [
        {"statement_id": "JSON01", "review": "The blush is too pigmented.", "product_category": "Blush", "channel": "AppStore"}
    ]
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f)

    db_path = str(tmp_path / "test_csv_json.duckdb")
    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()

    csv_records = ingestor.ingest_file(csv_file)
    assert len(csv_records) == 2
    db.insert_normalized_records(csv_records)

    json_records = ingestor.ingest_file(json_file)
    assert len(json_records) == 1
    db.insert_normalized_records(json_records)

    stats = db.get_stats_summary()
    assert stats["total_raw_records"] == 3
