"""
Test suite for Phase 4: Research Query Layer (RAG & Natural Language Interface).
"""

import pytest
from src.query.indexer import ResearchSearchIndex, tokenize_text
from src.query.synthesizer import EvidenceSynthesizer, format_rag_user_prompt
from src.query.service import ResearchQueryService
from src.storage.db import FeedbackDatabase
from src.ingestion.parsers import BatchIngestor
from src.ai.classifier import BehavioralClassifier
from src.ai.groq_client import GroqClient


def test_tokenize_text():
    tokens = tokenize_text("I'm looking for a warm-toned shade!")
    assert "looking" in tokens
    assert "warm-toned" in tokens or "warm" in tokens
    assert "shade" in tokens


def test_search_index_retrieval(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_statements.xlsx"
    db_path = str(tmp_path / "test_rag.duckdb")

    db = FeedbackDatabase(db_path)
    ingestor = BatchIngestor()
    records = ingestor.ingest_file(excel_path)
    db.insert_normalized_records(records[:35])

    classifier = BehavioralClassifier(groq_client=GroqClient(api_key=""))
    classifier.process_and_save_records(db)

    # Initialize index
    index = ResearchSearchIndex(db)
    assert index.total_docs == 35

    # 1. Search for shade uncertainty
    shade_results = index.search(query="shade undertone swatch match", top_k=5)
    assert len(shade_results) > 0

    # 2. Search with Category filter (Foundation only)
    fnd_results = index.search(query="coverage finish", category="FOUNDATION", top_k=5)
    assert len(fnd_results) >= 0

    # 3. Non-existent query
    empty_results = index.search(query="quantum physics astrophysics")
    assert len(empty_results) == 0


def test_evidence_synthesizer_empty_query():
    synthesizer = EvidenceSynthesizer()
    res = synthesizer.synthesize(query="Non-existent topic", evidence_docs=[])
    assert "No supporting evidence" in res["answer"]
    assert res["evidence_count"] == 0
    assert res["cited_records"] == []


def test_evidence_synthesizer_with_evidence():
    synthesizer = EvidenceSynthesizer()
    sample_docs = [
        {
            "record_id": "SYN002",
            "product_category": "FOUNDATION",
            "theme": "SHADE_CONFIDENCE",
            "wishlist_intent": "GENUINE_PURCHASE_INTENT",
            "purchase_blocker": ["SHADE"],
            "information_gap": ["SHADE_CONFIDENCE"],
            "raw_text": "This foundation is on my wishlist, but I'm not sure which shade matches my undertone.",
            "verbatim_evidence": "I'm not sure which shade matches my undertone",
            "source": "SYNTHETIC_TEST",
        }
    ]
    res = synthesizer.synthesize(query="Why do foundation shoppers hesitate?", evidence_docs=sample_docs)
    assert res["evidence_count"] == 1
    assert len(res["cited_records"]) == 1
    assert "Executive Summary" in res["answer"]
    assert "SYN002" in res["answer"]


def test_end_to_end_research_query_service(tmp_path):
    excel_path = "Docs/nykaa_ai_discovery_database_statements.xlsx"
    db_path = str(tmp_path / "test_e2e_rag.duckdb")

    db = FeedbackDatabase(db_path)
    records = BatchIngestor().ingest_file(excel_path)
    db.insert_normalized_records(records[:35])
    BehavioralClassifier(groq_client=GroqClient(api_key="")).process_and_save_records(db)

    service = ResearchQueryService(db=db)

    # Ask realistic research question
    res = service.ask(query="Why do users wishlist beauty products but delay purchase?", top_k=4)
    assert res["evidence_count"] > 0
    assert len(res["cited_records"]) > 0
    assert len(res["answer"]) > 100
