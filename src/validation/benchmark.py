"""
100-Sample Gold Standard Benchmark & Quality Evaluation Engine.
Computes Precision, Recall, Macro-F1, Accuracy, and Cohen's Kappa against human-annotated ground truth.
"""

import math
from typing import List, Dict, Any, Tuple
from ..ai.classifier import BehavioralClassifier
from ..ai.groq_client import GroqClient
from ..storage.db import FeedbackDatabase


# 100 curated representative beauty shopping statements with expert gold-standard ground truth annotations
GOLD_STANDARD_100: List[Dict[str, Any]] = [
    # 1-10: Shade & Tone Confidence
    {"id": "BM001", "category": "FOUNDATION", "text": "I really love the finish but I have no idea if 220 or 230 matches my warm olive undertone.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM002", "category": "LIPSTICK", "text": "The shade looks so berry-red on the model, but I'm worried it will look too bright on my dusky skin tone.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM003", "category": "CONCEALER", "text": "I need a swatch of this concealer in natural outdoor lighting to check if it oxidizes.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM004", "category": "FOUNDATION", "text": "Saved to wishlist, waiting to visit a physical store to swatch the shade on my jawline.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM005", "category": "BLUSH", "text": "Is this peachy pink blush too light for deeper skin tones? Wish they had swatches on diverse complexions.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM006", "category": "LIP_GLOSS", "text": "The brown gloss looks sheer, but I want to see how pigmented it is on pigmented lips.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM007", "category": "FOUNDATION", "text": "Every foundation I try turns ashy on my face. Need undertone shade finder before buying.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM008", "category": "CONCEALER", "text": "I cannot tell whether shade Medium Warm will neutralize my dark circles without creasing.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM009", "category": "LIPSTICK", "text": "Looking for a true nude for Indian wheatish skin tone. Can't figure out the right match.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM010", "category": "POWDER", "text": "Is the banana powder too yellow for cool undertones? Needs clearer swatch photos.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},

    # 11-20: Price, Discount & Perceived Value
    {"id": "BM011", "category": "SERUM", "text": "50ml for Rs 3,500 is very steep. I have it saved in my wishlist waiting for the Pink Friday sale discount.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM012", "category": "FOUNDATION", "text": "This luxury foundation is out of my monthly budget right now. Wish they offered a 15ml mini travel size.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM013", "category": "MOISTURIZER", "text": "I won't purchase at full MRP. Keeping in wishlist until there is a Buy 1 Get 1 or 30% coupon.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM014", "category": "PERFUME", "text": "Rs 8,000 is too risky to blind-buy. Release a 5ml discovery sample vial first.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM015", "category": "HAIR_CARE", "text": "The hair mask is expensive. Want to know if the quantity justifies the cost for curly hair.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM016", "category": "EYESHADOW", "text": "Palette price is too high when I only plan to use 3 out of 12 shades.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM017", "category": "LIPSTICK", "text": "Too pricey for everyday wear. Waiting for bank card discount to check out.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM018", "category": "SUNSCREEN", "text": "Rs 900 for just 50g sunscreen is hard to repurchase monthly. Looking for value bundles.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM019", "category": "FACE_OIL", "text": "High price point makes me hesitate. Waiting for clearance deals.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM020", "category": "SERUM", "text": "I love the ingredients but Rs 2,200 is steep. Waiting for festive discount code.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},

    # 21-30: Formula Suitability & Skin Sensitivity
    {"id": "BM021", "category": "SERUM", "text": "I have acne-prone sensitive skin and I'm worried this 10% Niacinamide will cause severe purging.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM022", "category": "SUNSCREEN", "text": "Will this sunscreen leave a greasy film or white cast on oily T-zone in humid weather?", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "FINISH"},
    {"id": "BM023", "category": "MOISTURIZER", "text": "Is this cream non-comedogenic? I cannot risk clogged pores and cystic breakouts.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM024", "category": "CLEANSER", "text": "Does this foaming cleanser strip moisture from dry sensitive barrier?", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM025", "category": "FOUNDATION", "text": "My skin gets very flaky around the nose. Need a hydrating dewy finish that doesn't cling to dry patches.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "FINISH"},
    {"id": "BM026", "category": "EXFOLIATOR", "text": "Is 2% BHA safe for beginners with rosacea? Need clear usage frequency guidance.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM027", "category": "HAIR_OIL", "text": "Will this oil weigh down fine low-porosity hair? Stored in wishlist while researching.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM028", "category": "RETINOL", "text": "Scared of irritation and barrier damage. Checking if it contains soothing ceramides.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM029", "category": "SUNSCREEN", "text": "I need to know if this mineral sunscreen stings sensitive eyes during workouts.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM030", "category": "TONER", "text": "Does this toner contain essential oils or added fragrance? My skin reacts badly to scents.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "INGREDIENT_SAFETY"},

    # 31-40: Quality, Authenticity & Wear Longevity
    {"id": "BM031", "category": "MASCARA", "text": "Some reviews claim it smudges under eyes after 3 hours and flakes into contact lenses.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM032", "category": "PERFUME", "text": "Want to know if the projection lasts beyond 4 hours before committing to a 100ml bottle.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM033", "category": "LIPSTICK", "text": "Is this truly transfer-proof and smudge-proof during meals, or does it fade in patches?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM034", "category": "EYELINER", "text": "Looking for waterproof gel liner that stays intact on oily hooded eyelids all day.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM035", "category": "FOUNDATION", "text": "I read mixed reviews about formula separation and cakey texture after long wear.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM036", "category": "SETTING_SPRAY", "text": "Does the spray nozzle mist evenly or does it spit large water droplets on makeup?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM037", "category": "SERUM", "text": "Worried the Vitamin C serum will oxidize to dark orange before I can finish the bottle.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM038", "category": "LIP_BALM", "text": "Does this actually heal cracked lips or does it just create a temporary waxy film?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM039", "category": "HAIR_SERUM", "text": "Does it control extreme humidity frizz without making roots greasy?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM040", "category": "BLUSH", "text": "Reviews say the blush pigment fades completely after 2 hours. Hesitating to buy.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},

    # 41-50: Cross-Product Comparison & Dupe Hunting
    {"id": "BM041", "category": "LIPSTICK", "text": "Comparing this luxury lipstick with an affordable Maybelline dupe before buying.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM042", "category": "SERUM", "text": "Debating between The Ordinary Niacinamide and Minimalist 10% on my wishlist.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM043", "category": "FOUNDATION", "text": "Comparing coverage side-by-side with L'Oreal True Match on YouTube swatch videos.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM044", "category": "SUNSCREEN", "text": "Checking if this Korean sunscreen is better than Japanese Biore UV watery essence.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM045", "category": "MOISTURIZER", "text": "Trying to choose between Cerave cream and Cetaphil lotion for winter barrier repair.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM046", "category": "BLUSH", "text": "Looking for comparison swatches between Rare Beauty blush in Hope versus Joy.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM047", "category": "PERFUME", "text": "Is this a good clone for Baccarat Rouge 540? Reading Reddit comparison threads.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM048", "category": "MASCARA", "text": "Saved both Sky High and Lash Sensational to compare which gives better curl volume.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM049", "category": "CONCEALER", "text": "Comparing Tarte Shape Tape coverage with Too Faced Born This Way concealer.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM050", "category": "HAIR_MASK", "text": "Comparing Olaplex No. 3 with K18 peptide mask reviews before investing.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},

    # 51-60: Intent Decay & Passive Wishlisting
    {"id": "BM051", "category": "EYESHADOW", "text": "Saved this colorful palette 6 months ago for a wedding, but now I don't really need it.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM052", "category": "LIPSTICK", "text": "I already own 5 very similar nude lipsticks in my collection. Don't really need another.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM053", "category": "BODY_LOTION", "text": "Added to wishlist on a whim during browsing. Will probably remove it during cleanup.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM054", "category": "PERFUME", "text": "Liked the fragrance note description initially, but lost interest over time.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM055", "category": "HAIR_TOOL", "text": "I wishlisted the hair curler but I rarely style my hair anyway.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM056", "category": "NAIL_POLISH", "text": "Saved 10 glitter nail paints in my wishlist just as aesthetic inspiration.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM057", "category": "HIGHLGHTER", "text": "Highlighters are out of my current daily makeup routine. Just sitting in wishlist.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM058", "category": "FACE_MIST", "text": "Impulse saved when I saw an influencer reel. Don't actually need a face mist.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM059", "category": "LIP_SCRUB", "text": "Realized I can just make a brown sugar scrub at home. No urgent reason to purchase.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM060", "category": "EYEBROW", "text": "Wishlisted when my brow pencil ran low, but bought a local alternative instead.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},

    # 61-70: Multi-Factor & Format/Size Blockers
    {"id": "BM061", "category": "PERFUME", "text": "I wish they had a 10ml travel spray because 100ml is too big and expensive to commit to.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM062", "category": "FOUNDATION", "text": "Why is there no mini bottle available to test the shade match and texture on my skin?", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM063", "category": "SERUM", "text": "Need a trial size kit before buying full 30ml bottles that might break me out.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM064", "category": "LIPSTICK", "text": "Mini combo set is out of stock. Not willing to buy the single full-size lipstick.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM065", "category": "SHAMPOO", "text": "1 Litre bottle is too huge. Bring back the 250ml size so I can test if it reduces dandruff.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SIZE_FORMAT"},
    {"id": "BM066", "category": "SUNSCREEN", "text": "Is this sunscreen silicone-based or water-based? Cannot tell if it will pill under my silicone foundation.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "INGREDIENT_SAFETY"},
    {"id": "BM067", "category": "LIPSTICK", "text": "The bullet lipstick shade looks warm, but I'm checking Reddit swatches to verify it's not neon orange.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM068", "category": "FOUNDATION", "text": "I want a shade recommendation for NC35 skin tone. Too confused by the brand's numbering system.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM069", "category": "MOISTURIZER", "text": "Product is consistently out of stock during sales. Waiting for restock notification.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "OTHER"},
    {"id": "BM070", "category": "SERUM", "text": "Comparing ingredients with my current dermat-prescribed routine before ordering.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},

    # 71-80: Diverse Beauty Statements
    {"id": "BM071", "category": "EYELINER", "text": "Does this liquid eyeliner have a felt tip or a brush tip? Product description is unclear.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PACKAGING"},
    {"id": "BM072", "category": "COMPACT", "text": "Does this compact powder come with a mirror and puff sponge for on-the-go touchups?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PACKAGING"},
    {"id": "BM073", "category": "BODY_WASH", "text": "How strong is the vanilla scent? I don't want an artificial synthetic smell.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM074", "category": "LIP_TINT", "text": "Is shade Cherry Pink long-lasting and water-resistant for daily college wear?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM075", "category": "CONCEALER", "text": "Looking for shade match for golden undertones. The digital camera swatches look inaccurate.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM076", "category": "SERUM", "text": "High percentage of AHA might be too strong for dry winter skin. Consulting dermat first.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM077", "category": "SUNSCREEN", "text": "Checking if this fluid sunscreen pills when layered on top of Vitamin C serum.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "FINISH"},
    {"id": "BM078", "category": "LIPSTICK", "text": "The price is great on sale, but I want to make sure the matte formula isn't crumbly.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "FINISH"},
    {"id": "BM079", "category": "FOUNDATION", "text": "Is this full coverage or buildable medium coverage? Need a natural skin-like finish.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "FINISH"},
    {"id": "BM080", "category": "MASCARA", "text": "Is it easy to remove with micellar water or does it pull out eyelashes during cleansing?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},

    # 81-90: Cross-Category Statements
    {"id": "BM081", "category": "HAIR_SERUM", "text": "Rs 1,800 is a bit much. Waiting for Diwali coupon code to save Rs 400.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM082", "category": "BLUSH", "text": "Looking for swatch video on warm brown skin tone to see if the shimmer is too chunky.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM083", "category": "TONER", "text": "Will this alcohol-free toner tighten enlarged pores without drying my cheeks?", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "SUITABILITY"},
    {"id": "BM084", "category": "PERFUME", "text": "Comparing top notes with Zara Gardenia on fragrantica before checking out.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM085", "category": "LIP_GLOSS", "text": "Wishlisted 3 shades of gloss, waiting for Buy 2 Get 1 offer to purchase all of them.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM086", "category": "FOUNDATION", "text": "Can someone tell me the MAC shade equivalent for shade Warm Honey?", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM087", "category": "SUNSCREEN", "text": "Saved 4 sunscreens. Reading Reddit skincare addiction India to pick the best matte one.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM088", "category": "CLEANSER", "text": "Does this oil cleanser emulsify completely with water without leaving a greasy blur on eyes?", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM089", "category": "MOISTURIZER", "text": "High price makes me pause. Looking for a drug store alternative with identical ceramide ratio.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM090", "category": "EYESHADOW", "text": "Saved the palette for special occasions, but I rarely do heavy eye makeup anymore.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},

    # 91-100: Final Validation Cohort
    {"id": "BM091", "category": "FOUNDATION", "text": "The shade chart online is completely misleading. I need real daylight swatch photos on Indian skin.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM092", "category": "LIPSTICK", "text": "I have cool undertones and reddish lips; need to know if this mauve lipstick leans grey.", "ground_truth_theme": "SHADE_CONFIDENCE", "ground_truth_blocker": "SHADE"},
    {"id": "BM093", "category": "SERUM", "text": "Rs 3,000 is too expensive for a 30ml peptide serum. Wish they had affordable refills.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
    {"id": "BM094", "category": "MOISTURIZER", "text": "I have fungal acne. Need to double check every single ingredient against Sezia before buying.", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "INGREDIENT_SAFETY"},
    {"id": "BM095", "category": "SUNSCREEN", "text": "Will this mineral sunscreen leave a ghost-like white tint on medium skin?", "ground_truth_theme": "SUITABILITY", "ground_truth_blocker": "FINISH"},
    {"id": "BM096", "category": "PERFUME", "text": "I read complaints that recent batches have weaker sillage. Waiting to test at an airport kiosk.", "ground_truth_theme": "QUALITY_TRUST", "ground_truth_blocker": "PERFORMANCE_DOUBT"},
    {"id": "BM097", "category": "MASCARA", "text": "Comparing tubing mascara vs waterproof formula to see which is easier to wash off at night.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "COMPARISON"},
    {"id": "BM098", "category": "BLUSH", "text": "I already have 4 liquid blushes from last summer. Keeping in wishlist with no rush to buy.", "ground_truth_theme": "INTENT_DECAY", "ground_truth_blocker": "NO_NEED"},
    {"id": "BM099", "category": "FOUNDATION", "text": "Comparing Fenty 290 with Esteé Lauder 3W1 Tawny to determine identical undertone.", "ground_truth_theme": "COMPARISON", "ground_truth_blocker": "SHADE"},
    {"id": "BM100", "category": "LIPSTICK", "text": "Too expensive at Rs 2,500. Will purchase only when 40% discount goes live.", "ground_truth_theme": "PRICE_VALUE", "ground_truth_blocker": "PRICE"},
]


def calculate_cohens_kappa(rater1: List[str], rater2: List[str]) -> float:
    """
    Compute Cohen's Kappa coefficient (inter-rater agreement).
    kappa = (Po - Pe) / (1 - Pe)
    """
    if len(rater1) != len(rater2) or len(rater1) == 0:
        return 0.0

    n = len(rater1)
    categories = list(set(rater1).union(set(rater2)))

    # Observed agreement Po
    po = sum(1 for a, b in zip(rater1, rater2) if a == b) / n

    # Expected chance agreement Pe
    c1 = {c: rater1.count(c) / n for c in categories}
    c2 = {c: rater2.count(c) / n for c in categories}
    pe = sum(c1.get(c, 0.0) * c2.get(c, 0.0) for c in categories)

    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


class BenchmarkEvaluator:
    """Executes gold standard evaluation across 100 sample benchmark."""

    def __init__(self, classifier: BehavioralClassifier = None):
        self.classifier = classifier or BehavioralClassifier(groq_client=GroqClient())

    def run_benchmark(self, sample_dataset: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        dataset = sample_dataset or GOLD_STANDARD_100
        gold_themes = []
        pred_themes = []

        tp = 0
        total = len(dataset)
        theme_metrics: Dict[str, Dict[str, int]] = {}

        for item in dataset:
            gold_theme = item["ground_truth_theme"]
            gold_themes.append(gold_theme)

            # Classify statement
            res = self.classifier.classify_text(
                raw_text=item["text"],
                product_category=item.get("category", "BEAUTY"),
                source="BENCHMARK",
                record_id=item["id"]
            )
            pred_theme = res.theme or "OTHER"
            pred_themes.append(pred_theme)

            # Init metrics
            if gold_theme not in theme_metrics:
                theme_metrics[gold_theme] = {"tp": 0, "fp": 0, "fn": 0}
            if pred_theme not in theme_metrics:
                theme_metrics[pred_theme] = {"tp": 0, "fp": 0, "fn": 0}

            if pred_theme == gold_theme:
                tp += 1
                theme_metrics[gold_theme]["tp"] += 1
            else:
                theme_metrics[pred_theme]["fp"] += 1
                theme_metrics[gold_theme]["fn"] += 1

        accuracy = tp / total if total > 0 else 0.0
        kappa = calculate_cohens_kappa(gold_themes, pred_themes)

        # Macro-F1 computation
        f1_scores = []
        per_theme_report = {}
        for theme, m in theme_metrics.items():
            prec = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) > 0 else 0.0
            rec = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0.0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
            f1_scores.append(f1)
            per_theme_report[theme] = {
                "precision": round(prec, 3),
                "recall": round(rec, 3),
                "f1": round(f1, 3),
                "samples": m["tp"] + m["fn"],
            }

        macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

        return {
            "total_benchmark_samples": total,
            "accuracy": round(accuracy, 4),
            "macro_f1": round(macro_f1, 4),
            "cohens_kappa": round(kappa, 4),
            "inter_rater_agreement_quality": "Near Perfect (>= 0.81)" if kappa >= 0.81 else ("Substantial (0.61 - 0.80)" if kappa >= 0.61 else "Moderate"),
            "meets_gate_threshold": bool(macro_f1 >= 0.85 and kappa >= 0.75),
            "per_theme_report": per_theme_report,
        }
