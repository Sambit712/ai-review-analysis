"""
File parsers and batch ingestion loader for Excel, CSV, and JSON datasets.
"""

import json
import os
from typing import List, Dict, Any, Optional
import pandas as pd
from ..models.schema import RawFeedbackRecord, NormalizedRecord
from .normalizer import normalize_raw_record
from .deduplicator import Deduplicator


COLUMN_MAPPING = {
    # Text column synonyms
    "text": "text",
    "review_text": "text",
    "comment": "text",
    "feedback": "text",
    "statement": "text",
    "review": "text",
    "user_feedback": "text",
    # ID synonyms
    "record_id": "record_id",
    "id": "record_id",
    "statement_id": "record_id",
    # Source synonyms
    "source": "source",
    "platform": "source",
    "channel": "source",
    # Category synonyms
    "product_category": "product_category",
    "category": "product_category",
    # URL synonyms
    "source_url": "source_url",
    "url": "source_url",
    "link": "source_url",
    # Date synonyms
    "date": "date",
    "timestamp": "date",
    "created_at": "date",
}


def map_row_to_raw_feedback(row: Dict[str, Any], default_source: str = "UPLOAD", fallback_idx: int = 1) -> RawFeedbackRecord:
    """Map arbitrary dictionary row to standard RawFeedbackRecord."""
    normalized_keys = {str(k).strip().lower(): v for k, v in row.items()}

    # Resolve text
    text_val = ""
    for alias in ["text", "review_text", "comment", "feedback", "statement", "review", "user_feedback"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            text_val = str(normalized_keys[alias]).strip()
            break

    # Resolve record_id
    rec_id = str(fallback_idx)
    for alias in ["record_id", "id", "statement_id"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            rec_id = str(normalized_keys[alias]).strip()
            break

    # Resolve source
    src_val = default_source
    for alias in ["source", "platform", "channel"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            src_val = str(normalized_keys[alias]).strip()
            break

    # Resolve category
    cat_val = "OTHER"
    for alias in ["product_category", "category"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            cat_val = str(normalized_keys[alias]).strip()
            break

    # Resolve URL
    url_val = None
    for alias in ["source_url", "url", "link"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            url_val = str(normalized_keys[alias]).strip()
            break

    # Resolve date
    date_val = None
    for alias in ["date", "timestamp", "created_at"]:
        if alias in normalized_keys and pd.notna(normalized_keys[alias]):
            date_val = str(normalized_keys[alias]).strip()
            break

    return RawFeedbackRecord(
        record_id=rec_id,
        source=src_val,
        source_url=url_val,
        date=date_val,
        text=text_val,
        product_category=cat_val,
        metadata={"original_row": {str(k): str(v) for k, v in row.items() if pd.notna(v)}},
    )


class BatchIngestor:
    """Handles multi-format parsing, normalization, and deduplication of feedback records."""

    def __init__(self):
        self.deduplicator = Deduplicator()

    def parse_excel(self, file_path: str, sheet_name: Optional[str] = None) -> List[RawFeedbackRecord]:
        """Parse records from Excel workbook."""
        xls = pd.ExcelFile(file_path)
        actual_sheet = sheet_name or xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=actual_sheet)

        raw_records = []
        seen_ids = set()
        for idx, row in df.iterrows():
            rec = map_row_to_raw_feedback(row.to_dict(), default_source="EXCEL_UPLOAD", fallback_idx=idx + 1)
            if rec.text:  # Filter out blank rows
                if rec.record_id in seen_ids:
                    rec.record_id = f"{rec.record_id}_{idx + 1}"
                seen_ids.add(rec.record_id)
                raw_records.append(rec)
        return raw_records

    def parse_csv(self, file_path: str) -> List[RawFeedbackRecord]:
        """Parse records from CSV file."""
        df = pd.read_csv(file_path)
        raw_records = []
        seen_ids = set()
        for idx, row in df.iterrows():
            rec = map_row_to_raw_feedback(row.to_dict(), default_source="CSV_UPLOAD", fallback_idx=idx + 1)
            if rec.text:
                if rec.record_id in seen_ids:
                    rec.record_id = f"{rec.record_id}_{idx + 1}"
                seen_ids.add(rec.record_id)
                raw_records.append(rec)
        return raw_records

    def parse_json(self, file_path: str) -> List[RawFeedbackRecord]:
        """Parse records from JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_records = []
        seen_ids = set()
        if isinstance(data, list):
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    rec = map_row_to_raw_feedback(item, default_source="JSON_UPLOAD", fallback_idx=idx + 1)
                    if rec.text:
                        if rec.record_id in seen_ids:
                            rec.record_id = f"{rec.record_id}_{idx + 1}"
                        seen_ids.add(rec.record_id)
                        raw_records.append(rec)
        elif isinstance(data, dict):
            items = data.get("records") or data.get("feedback") or [data]
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    rec = map_row_to_raw_feedback(item, default_source="JSON_UPLOAD", fallback_idx=idx + 1)
                    if rec.text:
                        if rec.record_id in seen_ids:
                            rec.record_id = f"{rec.record_id}_{idx + 1}"
                        seen_ids.add(rec.record_id)
                        raw_records.append(rec)
        return raw_records

    def ingest_dict_list(self, records: List[Dict[str, Any]]) -> List[NormalizedRecord]:
        """Ingest directly from a list of record dictionaries."""
        raw_records = []
        seen_ids = set()
        for idx, item in enumerate(records):
            if isinstance(item, dict):
                rec = map_row_to_raw_feedback(item, default_source="API_FEEDBACK", fallback_idx=idx + 1)
                if rec.text:
                    if rec.record_id in seen_ids:
                        rec.record_id = f"{rec.record_id}_{idx + 1}"
                    seen_ids.add(rec.record_id)
                    raw_records.append(rec)

        normalized_records = [normalize_raw_record(r) for r in raw_records]
        return self.deduplicator.process_batch(normalized_records)

    def ingest_file(self, file_path: str, sheet_name: Optional[str] = None) -> List[NormalizedRecord]:
        """Load, normalize, and deduplicate records from any supported file."""
        ext = os.path.splitext(file_path)[1].lower()

        if ext in [".xlsx", ".xls"]:
            raw_records = self.parse_excel(file_path, sheet_name=sheet_name)
        elif ext == ".csv":
            raw_records = self.parse_csv(file_path)
        elif ext == ".json":
            raw_records = self.parse_json(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported formats: .xlsx, .xls, .csv, .json")

        # 1. Normalize
        normalized_records = [normalize_raw_record(r) for r in raw_records]

        # 2. Deduplicate
        deduped_records = self.deduplicator.process_batch(normalized_records)

        return deduped_records
