"""
Data models and taxonomy definitions for AI Discovery Engine.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ProcessingStatus(str, Enum):
    """Lifecycle state machine for feedback records."""
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    CLASSIFIED = "PROCESSED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    NEEDS_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class WishlistIntent(str, Enum):
    GENUINE_PURCHASE_INTENT = "GENUINE_PURCHASE_INTENT"
    BOOKMARK = "BOOKMARK"
    COMPARISON = "COMPARISON"
    WAITING_FOR_RIGHT_TIME = "WAITING_FOR_RIGHT_TIME"
    WAITING_FOR_BETTER_VALUE = "WAITING_FOR_BETTER_VALUE"
    INSPIRATION = "INSPIRATION"
    FUTURE_NEED = "FUTURE_NEED"
    UNCERTAIN = "UNCERTAIN"
    OTHER = "OTHER"


class PurchaseBlocker(str, Enum):
    PRICE_VALUE = "PRICE_VALUE"
    PRICE = "PRICE"
    SHADE = "SHADE"
    FINISH = "FINISH"
    SUITABILITY = "SUITABILITY"
    QUALITY = "QUALITY"
    QUALITY_TRUST = "QUALITY_TRUST"
    REVIEWS_SOCIAL_PROOF = "REVIEWS_SOCIAL_PROOF"
    COMPARISON = "COMPARISON"
    ALTERNATIVE_FOUND = "ALTERNATIVE_FOUND"
    FORGOT = "FORGOT"
    TIMING_OCCASION = "TIMING_OCCASION"
    AVAILABILITY = "AVAILABILITY"
    RETURNS = "RETURNS"
    TRUST = "TRUST"
    NO_NEED = "NO_NEED"
    SIZE_FORMAT = "SIZE_FORMAT"
    INGREDIENT_SAFETY = "INGREDIENT_SAFETY"
    PACKAGING = "PACKAGING"
    PERFORMANCE_DOUBT = "PERFORMANCE_DOUBT"
    OTHER = "OTHER"


class InformationGap(str, Enum):
    SHADE_CONFIDENCE = "SHADE_CONFIDENCE"
    PRODUCT_QUALITY = "PRODUCT_QUALITY"
    PERFORMANCE = "PERFORMANCE"
    SUITABILITY = "SUITABILITY"
    INGREDIENTS = "INGREDIENTS"
    PRICE_VALUE = "PRICE_VALUE"
    REVIEWS = "REVIEWS"
    RETURN_POLICY = "RETURN_POLICY"
    DELIVERY = "DELIVERY"
    SOCIAL_PROOF = "SOCIAL_PROOF"
    COMPARISON = "COMPARISON"
    OTHER = "OTHER"


class ComparisonType(str, Enum):
    OTHER_BRAND = "OTHER_BRAND"
    SAME_PRODUCT_OTHER_PLATFORM = "SAME_PRODUCT_OTHER_PLATFORM"
    SIMILAR_PRODUCT = "SIMILAR_PRODUCT"
    PRICE = "PRICE"
    OFFER = "OFFER"
    DELIVERY = "DELIVERY"
    RETURNS = "RETURNS"
    QUALITY = "QUALITY"
    REVIEWS = "REVIEWS"
    OTHER = "OTHER"
    NONE = "NONE"


class ExternalResearch(str, Enum):
    NONE = "NONE"
    GOOGLE = "GOOGLE"
    YOUTUBE = "YOUTUBE"
    INSTAGRAM = "INSTAGRAM"
    REDDIT = "REDDIT"
    OTHER_MARKETPLACE = "OTHER_MARKETPLACE"
    OFFLINE_STORE = "OFFLINE_STORE"
    FRIENDS = "FRIENDS"
    OTHER = "OTHER"


class DecisionTrigger(str, Enum):
    LOWER_PRICE = "LOWER_PRICE"
    BETTER_VALUE = "BETTER_VALUE"
    BETTER_REVIEWS = "BETTER_REVIEWS"
    SHADE_CONFIRMATION = "SHADE_CONFIRMATION"
    SUITABILITY_CONFIDENCE = "SUITABILITY_CONFIDENCE"
    PRODUCT_DEMO = "PRODUCT_DEMO"
    BETTER_ALTERNATIVE = "BETTER_ALTERNATIVE"
    AVAILABILITY = "AVAILABILITY"
    OCCASION = "OCCASION"
    REPLENISHMENT = "REPLENISHMENT"
    SOCIAL_PROOF = "SOCIAL_PROOF"
    OTHER = "OTHER"


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"


class RawFeedbackRecord(BaseModel):
    """Immutable raw feedback representation."""
    record_id: str
    source: str
    source_url: Optional[str] = None
    date: Optional[str] = None
    text: str
    product_category: Optional[str] = "OTHER"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text_hash: Optional[str] = None
    status: ProcessingStatus = ProcessingStatus.NEW
    ingested_at: Optional[str] = None


class NormalizedRecord(BaseModel):
    """Sanitized and standardized feedback record ready for analysis."""
    record_id: str
    source: str
    source_url: Optional[str] = None
    date: str
    raw_text: str
    cleaned_text: str
    product_category: str
    text_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_duplicate: bool = False
    canonical_record_id: Optional[str] = None
    status: ProcessingStatus = ProcessingStatus.NEW
    ingested_at: str


class BehavioralRecord(BaseModel):
    """Enriched behavioral dimensions extracted via AI."""
    record_id: str
    wishlist_intent: Optional[WishlistIntent] = WishlistIntent.OTHER
    purchase_blocker: List[PurchaseBlocker] = Field(default_factory=list)
    information_gap: List[InformationGap] = Field(default_factory=list)
    comparison_behavior: bool = False
    comparison_type: List[ComparisonType] = Field(default_factory=list)
    external_research: List[ExternalResearch] = Field(default_factory=list)
    decision_trigger: List[DecisionTrigger] = Field(default_factory=list)
    sentiment: Optional[Sentiment] = Sentiment.NEUTRAL
    confidence_score: float = Field(ge=0.0, le=1.0, default=1.0)
    verbatim_evidence: Optional[str] = None
    theme: Optional[str] = None
    segment: Optional[str] = None
    status: ProcessingStatus = ProcessingStatus.PROCESSED
    model_version: Optional[str] = "llama-3.3-70b-versatile"
    error_message: Optional[str] = None
    analyzed_at: Optional[str] = None


class IngestionAuditReport(BaseModel):
    """Execution audit report for incremental batch ingestion."""
    batch_id: str
    total_received: int
    duplicates_rejected: int
    new_records_ingested: int
    classified_count: int
    flagged_review_count: int
    failed_count: int
    duration_ms: float
    timestamp: str
    insights_recalculated: bool = True


# Synonyms / Aliases for backward & multi-module compatibility
NormalizedFeedbackRecord = NormalizedRecord
TaxonomyClassificationOutput = BehavioralRecord
