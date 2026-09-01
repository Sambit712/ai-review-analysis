"""
Test suite for Phase 5: FastAPI Discovery Dashboard Endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.storage.db import FeedbackDatabase
from src.ingestion.parsers import BatchIngestor
from src.ai.classifier import BehavioralClassifier
from src.ai.groq_client import GroqClient


@pytest.fixture(scope="module")
def client():
    # Ensure database has sample records ingested & classified
    db = FeedbackDatabase()
    ingestor = BatchIngestor()
    db.insert_normalized_records(ingestor.ingest_file("Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx"))
    BehavioralClassifier(groq_client=GroqClient()).process_and_save_records(db)
    
    with TestClient(app) as c:
        yield c


def test_get_overview(client):
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["total_raw_records"] >= 35
    assert data["total_analyzed_records"] >= 35
    assert "average_confidence_score" in data


def test_get_analytics_themes(client):
    res = client.get("/api/analytics/themes")
    assert res.status_code == 200
    data = res.json()
    assert len(data) > 0
    assert "theme_id" in data[0]
    assert "frequency_pct" in data[0]


def test_get_analytics_blockers(client):
    # Overall
    res = client.get("/api/analytics/blockers")
    assert res.status_code == 200
    data = res.json()
    assert len(data) > 0
    assert "blocker" in data[0]

    # Category filtered
    res_cat = client.get("/api/analytics/blockers?category=FOUNDATION")
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert len(data_cat) > 0


def test_get_opportunities(client):
    res = client.get("/api/opportunities?shade_solv=5.0&price_rel=4.0")
    assert res.status_code == 200
    data = res.json()
    assert len(data) > 0
    assert data[0]["opportunity_score"] > 0
    assert "evidence_quotes" in data[0]


def test_get_evidence_endpoint(client):
    # Basic evidence lookup
    res = client.get("/api/evidence?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 35
    assert len(data["records"]) <= 10

    # Search filter with match
    res_search = client.get("/api/evidence?search=shade")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert 0 < search_data["total"] <= data["total"]
    for rec in search_data["records"]:
        searchable_text = f"{rec.get('raw_text', '')} {rec.get('verbatim_evidence', '')} {rec.get('record_id', '')} {rec.get('product_category', '')} {rec.get('theme', '')}".lower()
        assert "shade" in searchable_text

    # Search filter with no match
    res_no_match = client.get("/api/evidence?search=nonexistent_xyz_query_12345")
    assert res_no_match.status_code == 200
    assert res_no_match.json()["total"] == 0
    assert len(res_no_match.json()["records"]) == 0



def test_post_ask_query(client):
    res = client.post("/api/query/ask", json={"query": "Why do users hesitate before buying foundation?", "top_k": 3})
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert data["evidence_count"] > 0


def test_serve_dashboard_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "AuraInsights" in res.text
    assert "Executive Intelligence Overview" in res.text
