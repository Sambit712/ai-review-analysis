"""
Text sanitization, schema normalization, and category standardization.
"""

import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from ..models.schema import RawFeedbackRecord, NormalizedRecord


CATEGORY_NORMALIZATION_MAP = {
    "lipstick": "LIPSTICK",
    "lip gloss": "LIP_GLOSS",
    "lipgloss": "LIP_GLOSS",
    "foundation": "FOUNDATION",
    "serum": "SERUM",
    "blush": "BLUSH",
    "mascara": "MASCARA",
    "sunscreen": "SUNSCREEN",
    "concealer": "CONCEALER",
    "skincare": "SKINCARE",
    "fashion": "FASHION",
    "fashion (non-beauty)": "FASHION",
    "exploratory fashion wishlist response": "FASHION",
}

SOURCE_NORMALIZATION_MAP = {
    "survey": "SURVEY",
    "synthetic test": "SYNTHETIC_TEST",
    "reddit": "REDDIT",
    "youtube": "YOUTUBE",
    "app_store": "APP_STORE",
    "play_store": "PLAY_STORE",
    "product_review": "PRODUCT_REVIEW",
}


def sanitize_text(text: str) -> str:
    """Normalize whitespace and control characters without altering verbatim meaning."""
    if not text:
        return ""
    # Replace smart quotes and special unicode dashes
    cleaned = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    cleaned = cleaned.replace("—", "-").replace("–", "-")
    # Replace replacement character (\ufffd) with apostrophe if present
    cleaned = cleaned.replace("\ufffd", "'")
    # Collapse multiple whitespace characters into single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def compute_text_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized text."""
    normalized_for_hash = sanitize_text(text).lower()
    return hashlib.sha256(normalized_for_hash.encode("utf-8")).hexdigest()


def normalize_category(category_input: Optional[str]) -> str:
    """Standardize category to canonical uppercase enum-like string."""
    if not category_input:
        return "OTHER"
    cat_str = str(category_input).strip().lower()
    for key, val in CATEGORY_NORMALIZATION_MAP.items():
        if key in cat_str:
            return val
    return cat_str.upper().replace(" ", "_")


def normalize_source(source_input: Optional[str]) -> str:
    """Standardize source to canonical uppercase source name."""
    if not source_input:
        return "UNKNOWN"
    src_str = str(source_input).strip().lower()
    for key, val in SOURCE_NORMALIZATION_MAP.items():
        if key in src_str:
            return val
    return src_str.upper().replace(" ", "_")


def normalize_raw_record(raw: RawFeedbackRecord) -> NormalizedRecord:
    """Transform raw feedback into normalized record."""
    cleaned_txt = sanitize_text(raw.text)
    txt_hash = compute_text_hash(cleaned_txt)
    iso_date = raw.date if raw.date else datetime.now(timezone.utc).isoformat()
    ingested_time = raw.ingested_at if raw.ingested_at else datetime.now(timezone.utc).isoformat()

    return NormalizedRecord(
        record_id=str(raw.record_id),
        source=normalize_source(raw.source),
        source_url=raw.source_url,
        date=iso_date,
        raw_text=raw.text,
        cleaned_text=cleaned_txt,
        product_category=normalize_category(raw.product_category),
        text_hash=txt_hash,
        metadata=raw.metadata,
        is_duplicate=False,
        canonical_record_id=None,
        ingested_at=ingested_time,
    )
