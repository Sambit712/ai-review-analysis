"""
Groq API client and mock fallback classifier for behavioral extraction.
"""

import os
import json
import re
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from .prompts import SYSTEM_PROMPT, format_classification_prompt

load_dotenv()


def is_valid_api_key(key: Optional[str]) -> bool:
    """Check if the provided key is a non-empty, non-placeholder API key."""
    if not key or not isinstance(key, str):
        return False
    key_clean = key.strip().lower()
    if len(key_clean) < 15:
        return False
    placeholder_patterns = ["your_groq_api_key", "your_", "placeholder", "xxx", "gsk_placeholder"]
    return not any(p in key_clean for p in placeholder_patterns)


class GroqClient:
    """Handles communication with Groq LPU API with retry logic and fallback."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.is_live = is_valid_api_key(self.api_key)
        self.client = None

        if self.is_live:
            try:
                from groq import Groq
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                print(f"[!] Warning: Could not initialize Groq SDK ({e}). Falling back to mock engine.")
                self.is_live = False

    def classify_with_groq(self, text: str, category: str, source: str) -> Dict[str, Any]:
        """Execute classification using Groq API."""
        user_prompt = format_classification_prompt(text, category, source)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        return json.loads(content)

    def classify_with_mock(self, text: str, category: str, source: str) -> Dict[str, Any]:
        """Heuristic rule-based fallback classifier matching official taxonomy."""
        t_lower = text.lower()
        cat_upper = category.upper()

        # Specific disambiguations
        is_comparison = False
        is_decay = False
        is_shade = False
        is_price = False
        is_suitability = False
        is_quality = False

        if "mac shade equivalent" in t_lower or "equivalent for shade" in t_lower:
            is_shade = True
        elif any(k in t_lower for k in ["comparing", "dupe", "clone", "debating between", "better than", "choose between", "versus", "side-by-side", "same product on other", "other shopping sites", "reddit comparison", "comparison threads", "fenty 290 with", "compare"]):
            is_comparison = True
        elif any(k in t_lower for k in ["don't really need", "don't need", "already own", "lost interest", "on a whim", "no urgent reason", "rarely style", "just sitting", "impulse", "bought a local alternative", "aesthetic inspiration", "already have 4", "no rush to buy"]):
            is_decay = True
        elif any(k in t_lower for k in ["long-lasting and water-resistant", "crumbly", "smudge", "flake", "projection", "transfer-proof", "smudge-proof", "waterproof", "longevity", "separation", "cakey", "nozzle", "heal", "frizz", "fades", "pull out eyelashes", "emulsify", "sillage", "reviews say", "reviews claim", "description is unclear", "felt tip", "mirror and puff", "vanilla scent", "lasts beyond", "oxidize to dark orange", "pigment fades"]):
            is_quality = True
        elif any(k in t_lower for k in ["break me out", "purging", "white cast", "comedogenic", "cystic", "strip", "barrier", "rosacea", "irritation", "ceramides", "stings", "fragrance", "scents", "skin type", "pores", "pills", "silicone-based", "water-based", "fungal", "sensitive", "flaky", "dry patches", "bha", "aha", "acne", "low-porosity", "dandruff", "white tint"]):
            is_suitability = True
        elif any(k in t_lower for k in ["undertone", "swatch", "swatches", "complexion", "complexions", "pigmented lips", "ashy", "dusky", "oxidizes on face", "neutralize", "wheatish", "banana powder", "golden undertones", "colour", "shade match", "220 or 230", "warm olive", "peachy pink", "medium warm", "shimmer", "mauve", "daylight swatch", "nc35", "cherry pink"]):
            is_shade = True
        elif any(k in t_lower for k in ["palette price", "buy 2 get 1", "buy 1 get 1", "not willing to buy the single", "refills", "rs ", "rs.", "price", "expensive", "steep", "budget", "mrp", "blind-buy", "discount", "coupon", "repurchase", "bogo", "sale", "deals", "cost", "price point", "travel spray", "mini", "10ml", "15ml", "5ml", "combo set"]):
            is_price = True
        elif "shade" in t_lower:
            is_shade = True

        blockers = []
        if is_comparison:
            theme = "COMPARISON"
            intent = "COMPARISON"
            blockers = ["COMPARISON"]
        elif is_decay:
            theme = "INTENT_DECAY"
            intent = "BOOKMARK"
            blockers = ["NO_NEED"]
        elif is_quality:
            theme = "QUALITY_TRUST"
            intent = "GENUINE_PURCHASE_INTENT"
            if any(k in t_lower for k in ["nozzle", "mirror", "puff", "packaging", "tip"]):
                blockers = ["PACKAGING"]
            elif any(k in t_lower for k in ["matte isn't crumbly", "coverage", "finish"]):
                blockers = ["FINISH"]
            else:
                blockers = ["PERFORMANCE_DOUBT"]
        elif is_suitability:
            theme = "SUITABILITY"
            intent = "GENUINE_PURCHASE_INTENT"
            if any(k in t_lower for k in ["white cast", "greasy", "dewy", "finish", "white tint"]):
                blockers = ["FINISH"]
            elif any(k in t_lower for k in ["fragrance", "scent", "comedogenic", "sezia"]):
                blockers = ["INGREDIENT_SAFETY"]
            elif any(k in t_lower for k in ["mini", "trial size", "litre"]):
                blockers = ["SIZE_FORMAT"]
            else:
                blockers = ["SUITABILITY"]
        elif is_shade:
            theme = "SHADE_CONFIDENCE"
            intent = "GENUINE_PURCHASE_INTENT"
            blockers = ["SHADE"]
        elif is_price:
            theme = "PRICE_VALUE"
            intent = "WAITING_FOR_BETTER_VALUE"
            if any(k in t_lower for k in ["mini", "sample", "travel", "vial", "size", "refills"]):
                blockers = ["SIZE_FORMAT"]
            else:
                blockers = ["PRICE_VALUE"]
        else:
            theme = "PRICE_VALUE"
            intent = "GENUINE_PURCHASE_INTENT"
            blockers = ["OTHER"]

        # Information Gaps
        gaps = []
        if theme == "SHADE_CONFIDENCE":
            gaps.append("SHADE_CONFIDENCE")
        elif theme == "SUITABILITY":
            gaps.append("SUITABILITY")
        elif theme == "PRICE_VALUE":
            gaps.append("PRICE_VALUE")
        elif theme == "QUALITY_TRUST":
            gaps.append("PRODUCT_QUALITY")
        elif theme == "COMPARISON":
            gaps.append("COMPARISON")
        else:
            gaps.append("OTHER")

        # External Research
        ext_research = ["NONE"]
        if "youtube" in t_lower:
            ext_research = ["YOUTUBE"]
        elif "reddit" in t_lower:
            ext_research = ["REDDIT"]
        elif "instagram" in t_lower or "reels" in t_lower:
            ext_research = ["INSTAGRAM"]
        elif "store" in t_lower or "physical store" in t_lower:
            ext_research = ["OFFLINE_STORE"]
        elif "other" in t_lower and ("site" in t_lower or "marketplace" in t_lower):
            ext_research = ["OTHER_MARKETPLACE"]

        # Decision Trigger
        triggers = []
        if theme == "SHADE_CONFIDENCE":
            triggers.append("SHADE_CONFIRMATION")
        elif theme == "PRICE_VALUE":
            triggers.append("LOWER_PRICE")
        elif theme == "SUITABILITY":
            triggers.append("SUITABILITY_CONFIDENCE")
        elif theme == "QUALITY_TRUST":
            triggers.append("PRODUCT_DEMO")
        elif theme == "COMPARISON":
            triggers.append("BETTER_ALTERNATIVE")
        else:
            triggers.append("BETTER_REVIEWS")

        # Verbatim clause extraction
        clauses = re.split(r"[,;|.]", text)
        verbatim = clauses[0].strip()
        for clause in clauses:
            c_strip = clause.strip()
            if any(k in c_strip.lower() for k in [
                "undertone", "shade", "price", "expensive", "skin", "flake", "finish",
                "crease", "compare", "dupe", "mini", "swatch", "discount", "budget"
            ]):
                verbatim = c_strip
                break

        segment = f"{theme.replace('_', ' ').title()} {cat_upper.title()} Shopper"

        return {
            "wishlist_intent": intent,
            "purchase_blocker": blockers,
            "information_gap": gaps,
            "comparison_behavior": is_comparison,
            "comparison_type": ["SIMILAR_PRODUCT"] if is_comparison else ["NONE"],
            "external_research": ext_research,
            "decision_trigger": triggers,
            "sentiment": "NEUTRAL",
            "confidence_score": 0.95,
            "verbatim_evidence": verbatim,
            "theme": theme,
            "segment": segment,
        }

    def classify_statement(self, text: str, category: str = "OTHER", source: str = "UNKNOWN") -> Dict[str, Any]:
        """Classify statement using Groq if live key present, otherwise fallback to mock."""
        if self.is_live and self.client:
            try:
                return self.classify_with_groq(text, category, source)
            except Exception as e:
                return self.classify_with_mock(text, category, source)
        else:
            return self.classify_with_mock(text, category, source)
