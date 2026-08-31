"""
Test suite for Phase 6: Validation Layer, Benchmark Evaluation & Human-in-the-Loop QA.
"""

import pytest
from src.validation.benchmark import BenchmarkEvaluator, calculate_cohens_kappa, GOLD_STANDARD_100
from src.validation.reviewer import HumanReviewManager
from src.storage.db import FeedbackDatabase
from src.ingestion.parsers import BatchIngestor
from src.ai.classifier import BehavioralClassifier
from src.ai.groq_client import GroqClient
from src.analytics.aggregator import AnalyticsAggregator
from src.analytics.opportunity_scorer import OpportunityScorer
from src.query.service import ResearchQueryService


def test_cohens_kappa_calculation():
    # 1. Perfect agreement
    r1 = ["SHADE_CONFIDENCE", "PRICE_VALUE", "SUITABILITY"]
    r2 = ["SHADE_CONFIDENCE", "PRICE_VALUE", "SUITABILITY"]
    assert calculate_cohens_kappa(r1, r2) == 1.0

    # 2. Partial agreement
    r3 = ["SHADE_CONFIDENCE", "PRICE_VALUE", "SUITABILITY", "QUALITY_TRUST"]
    r4 = ["SHADE_CONFIDENCE", "PRICE_VALUE", "SUITABILITY", "COMPARISON"]
    kappa = calculate_cohens_kappa(r3, r4)
    assert 0.5 <= kappa < 1.0


def test_100_sample_gold_standard_benchmark():
    evaluator = BenchmarkEvaluator(classifier=BehavioralClassifier(groq_client=GroqClient()))
    report = evaluator.run_benchmark(GOLD_STANDARD_100)

    assert report["total_benchmark_samples"] == 100
    assert report["accuracy"] >= 0.85, f"Accuracy {report['accuracy']} below 85% gate"
    assert report["macro_f1"] >= 0.85, f"Macro-F1 {report['macro_f1']} below 85% gate"
    assert report["cohens_kappa"] >= 0.75, f"Cohen's Kappa {report['cohens_kappa']} below 0.75"
    assert report["meets_gate_threshold"] is True
    assert "SHADE_CONFIDENCE" in report["per_theme_report"]
    assert "PRICE_VALUE" in report["per_theme_report"]


def test_human_in_the_loop_review_and_override(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"
    db_path = str(tmp_path / "test_human_review.duckdb")

    db = FeedbackDatabase(db_path)
    db.insert_normalized_records(BatchIngestor().ingest_file(excel_path))
    BehavioralClassifier(groq_client=GroqClient()).process_and_save_records(db)

    mgr = HumanReviewManager(db)

    # 1. Force a low confidence score on record 1 to test queue
    conn = db.get_connection()
    conn.execute("UPDATE behavioral_records SET confidence_score = 0.55, status = 'REVIEW_REQUIRED' WHERE record_id = '1'")
    conn.close()

    queue = mgr.get_review_queue(min_confidence_threshold=0.70)
    assert any(r["record_id"] == "1" for r in queue)

    # 2. Human reviewer overrides and approves record
    mgr.approve_or_override_classification(
        record_id="1",
        theme="PRICE_VALUE",
        wishlist_intent="GENUINE_PURCHASE_INTENT",
        purchase_blocker=["PRICE"]
    )

    # 3. Verify record updated to HUMAN_APPROVED with confidence 1.0
    conn = db.get_connection()
    rec = conn.execute("SELECT status, confidence_score, theme FROM behavioral_records WHERE record_id = '1'").fetchone()
    conn.close()

    assert rec[0] == "HUMAN_APPROVED"
    assert rec[1] == 1.0
    assert rec[2] == "PRICE_VALUE"


def test_full_pipeline_end_to_end_lifecycle(tmp_path):
    """
    Comprehensive End-to-End lifecycle test:
    Ingestion -> Classification -> Aggregation -> Opportunity Scoring -> RAG Search -> QA Review -> Benchmark
    """
    db_path = str(tmp_path / "test_e2e_full.duckdb")
    db = FeedbackDatabase(db_path)

    # 1. Ingest
    ingestor = BatchIngestor()
    records = ingestor.ingest_file("Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx")
    inserted = db.insert_normalized_records(records)
    assert inserted >= 35

    # 2. Classify
    classifier = BehavioralClassifier(groq_client=GroqClient())
    classified = classifier.process_and_save_records(db)
    assert len(classified) >= 35

    # 3. Deterministic Analytics
    agg = AnalyticsAggregator(db)
    overview = agg.get_overview_metrics()
    assert overview["total_analyzed_records"] >= 35
    themes = agg.get_theme_distribution()
    assert len(themes) > 0

    # 4. Opportunity Scoring
    scorer = OpportunityScorer(db)
    opps = scorer.compute_opportunity_rankings()
    assert len(opps) > 0
    assert opps[0]["opportunity_score"] > 0

    # 5. Natural Language Query
    query_service = ResearchQueryService(db)
    res = query_service.ask("Why do lipstick users abandon their wishlists?", top_k=3)
    assert res["evidence_count"] > 0
    assert len(res["cited_records"]) > 0

    # 6. Benchmark Evaluation
    evaluator = BenchmarkEvaluator(classifier=classifier)
    report = evaluator.run_benchmark(GOLD_STANDARD_100[:20])  # Fast subset
    assert report["accuracy"] >= 0.80
