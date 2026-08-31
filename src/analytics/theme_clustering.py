"""
Hierarchical Behavioral Theme Clustering Engine.
"""

from typing import Dict, List, Any
from ..models.schema import PurchaseBlocker, InformationGap


# Master taxonomy theme definitions and hierarchical mapping
THEME_TAXONOMY = {
    "SHADE_CONFIDENCE": {
        "name": "Shade Confidence & Swatch Clarity",
        "description": "Uncertainty regarding exact shade matching, undertones, real-world skin appearance, and swatch accuracy.",
        "primary_blockers": ["SHADE"],
        "primary_gaps": ["SHADE_CONFIDENCE"],
        "default_solvability": 4.5,
        "default_relevance": 4.8,
        "default_impact": 4.5,
    },
    "PRICE_VALUE": {
        "name": "Price, Value & Deal Hesitation",
        "description": "Hesitation due to price point, waiting for sales/coupons, finding cheaper alternatives, or shipping costs.",
        "primary_blockers": ["PRICE_VALUE", "SIZE_FORMAT"],
        "primary_gaps": ["PRICE_VALUE"],
        "default_solvability": 4.0,
        "default_relevance": 4.2,
        "default_impact": 4.8,
    },
    "SUITABILITY": {
        "name": "Skin Type Suitability & Safety",
        "description": "Doubts regarding compatibility with oily, dry, acne-prone, or sensitive skin, and white cast concerns.",
        "primary_blockers": ["SUITABILITY", "INGREDIENT_SAFETY"],
        "primary_gaps": ["SUITABILITY", "INGREDIENTS"],
        "default_solvability": 4.2,
        "default_relevance": 4.6,
        "default_impact": 4.3,
    },
    "QUALITY_TRUST": {
        "name": "Formula Performance & Trust",
        "description": "Worries regarding formula longevity, flaking, creasing, pigmentation, or product authenticity.",
        "primary_blockers": ["QUALITY", "QUALITY_TRUST", "PERFORMANCE_DOUBT", "PACKAGING", "REVIEWS_SOCIAL_PROOF", "TRUST", "FINISH"],
        "primary_gaps": ["PRODUCT_QUALITY", "PERFORMANCE", "REVIEWS"],
        "default_solvability": 3.8,
        "default_relevance": 4.4,
        "default_impact": 4.0,
    },
    "COMPARISON": {
        "name": "Alternative & Brand Comparison Paralysis",
        "description": "Paralysis from evaluating multiple competing brands, similar products, or cross-platform options.",
        "primary_blockers": ["COMPARISON", "ALTERNATIVE_FOUND"],
        "primary_gaps": ["COMPARISON"],
        "default_solvability": 4.0,
        "default_relevance": 3.9,
        "default_impact": 4.1,
    },
    "INTENT_DECAY": {
        "name": "Wishlist Decay & Forgetting",
        "description": "Saved items forgotten over time without decision triggers or clear replenishment reminders.",
        "primary_blockers": ["FORGOT", "TIMING_OCCASION", "NO_NEED"],
        "primary_gaps": ["OTHER"],
        "default_solvability": 4.6,
        "default_relevance": 3.5,
        "default_impact": 3.8,
    },
}


def map_blocker_to_theme(blockers: List[str]) -> str:
    """Deterministically assign a primary behavioral theme based on blockers."""
    if not blockers:
        return "PRICE_VALUE"

    blocker_set = {b.upper() for b in blockers}

    if "SHADE" in blocker_set:
        return "SHADE_CONFIDENCE"
    if any(b in blocker_set for b in ["PRICE_VALUE", "PRICE", "SIZE_FORMAT"]):
        return "PRICE_VALUE"
    if any(b in blocker_set for b in ["SUITABILITY", "INGREDIENT_SAFETY"]):
        return "SUITABILITY"
    if any(b in blocker_set for b in ["QUALITY", "QUALITY_TRUST", "PERFORMANCE_DOUBT", "PACKAGING", "REVIEWS_SOCIAL_PROOF", "TRUST", "FINISH"]):
        return "QUALITY_TRUST"
    if any(b in blocker_set for b in ["COMPARISON", "ALTERNATIVE_FOUND"]):
        return "COMPARISON"
    if any(b in blocker_set for b in ["FORGOT", "TIMING_OCCASION", "NO_NEED"]):
        return "INTENT_DECAY"

    return "PRICE_VALUE"
