"""
Test suite for Phase 3: Deterministic Analytics & Opportunity Scoring Engine.
"""

import pytest
from src.analytics.theme_clustering import THEME_TAXONOMY, map_blocker_to_theme
from src.analytics.aggregator import AnalyticsAggregator
from src.analytics.opportunity_scorer import OpportunityScorer
from src.storage.db import FeedbackDatabase
from src.ingestion.parsers import BatchIngestor
from src.ai.classifier import BehavioralClassifier
from src.ai.groq_client import GroqClient


def test_theme_mapping_rules():
    assert map_blocker_to_theme(["SHADE"]) == "SHADE_CONFIDENCE"
    assert map_blocker_to_theme(["PRICE_VALUE", "COMPARISON"]) == "PRICE_VALUE"
    assert map_blocker_to_theme(["SUITABILITY"]) == "SUITABILITY"
    assert map_blocker_to_theme(["QUALITY"]) == "QUALITY_TRUST"
    assert map_blocker_to_theme(["FORGOT"]) == "INTENT_DECAY"
    assert map_blocker_to_theme(["COMPARISON"]) == "COMPARISON"


def test_deterministic_aggregations(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"
    db_path = str(tmp_path / "test_phase3.duckdb")

    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()
    records = ingestor.ingest_file(excel_path)
    db.insert_normalized_records(records)

    # Classify all records
    classifier = BehavioralClassifier(groq_client=GroqClient())
    classifier.process_and_save_records(db)

    # Test aggregator
    agg = AnalyticsAggregator(db)
    overview = agg.get_overview_metrics()
    assert overview["total_raw_records"] == 35
    assert overview["total_analyzed_records"] == 35
    assert overview["average_confidence_score"] > 0.80

    # Test theme distribution
    themes = agg.get_theme_distribution()
    assert len(themes) > 0
    total_pct = sum(t["frequency_pct"] for t in themes)
    assert 99.5 <= total_pct <= 100.5, f"Expected total percentage ~100%, got {total_pct}"

    # Test blocker frequencies
    blockers = agg.get_blocker_frequencies()
    assert len(blockers) > 0
    assert any(b["blocker"] == "SHADE" for b in blockers)
    assert any(b["blocker"] == "PRICE_VALUE" for b in blockers)

    # Test category specific filtering (e.g. Foundation)
    fnd_blockers = agg.get_blocker_frequencies(category="FOUNDATION")
    assert len(fnd_blockers) > 0
    assert all(b["total_analyzed_base"] == 5 for b in fnd_blockers)

    # Test category breakdown matrix
    cat_matrix = agg.get_category_breakdown_matrix()
    assert "FOUNDATION" in cat_matrix
    assert "LIPSTICK" in cat_matrix
    assert cat_matrix["FOUNDATION"]["total"] == 5


def test_opportunity_scoring_formula(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"
    db_path = str(tmp_path / "test_opp_scorer.duckdb")

    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()
    records = ingestor.ingest_file(excel_path)
    db.insert_normalized_records(records)

    classifier = BehavioralClassifier(groq_client=GroqClient())
    classifier.process_and_save_records(db)

    scorer = OpportunityScorer(db)
    rankings = scorer.compute_opportunity_rankings()

    assert len(rankings) > 0
    top_opp = rankings[0]

    # Verify score formula: freq_ratio * rel * imp * solv * 10
    freq_ratio = top_opp["frequency_count"] / 35.0
    expected_score = round(freq_ratio * top_opp["purchase_relevance_1_5"] * top_opp["segment_impact_1_5"] * top_opp["solvability_1_5"] * 10, 2)
    assert top_opp["opportunity_score"] == expected_score

    # Check evidence quotes are attached
    assert len(top_opp["evidence_quotes"]) > 0

    # Verify database persistence
    conn = db.get_connection()
    try:
        saved_opps = conn.execute("SELECT COUNT(*) FROM opportunity_scores").fetchone()[0]
        assert saved_opps == len(rankings)
    finally:
        conn.close()


def test_custom_weight_overrides(tmp_path):
    db_path = str(tmp_path / "test_custom_weights.duckdb")
    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()
    db.insert_normalized_records(ingestor.ingest_file("Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"))

    classifier = BehavioralClassifier(groq_client=GroqClient())
    classifier.process_and_save_records(db)

    scorer = OpportunityScorer(db)
    custom = {
        "SHADE_CONFIDENCE": {
            "purchase_relevance": 5.0,
            "segment_impact": 5.0,
            "solvability": 5.0,
        }
    }
    rankings = scorer.compute_opportunity_rankings(custom_weights=custom)
    shade_opp = next(o for o in rankings if o["opportunity_theme"] == "SHADE_CONFIDENCE")
    assert shade_opp["purchase_relevance_1_5"] == 5.0
    assert shade_opp["solvability_1_5"] == 5.0
