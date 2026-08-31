"""
FastAPI REST Application for AI Discovery Engine.
Serves executive analytics, opportunity prioritizations, RAG research queries,
validation benchmarks, human-in-the-loop overrides, and incremental ingestion.
"""

import os
import shutil
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..storage.db import FeedbackDatabase
from ..analytics.aggregator import AnalyticsAggregator
from ..analytics.opportunity_scorer import OpportunityScorer
from ..query.service import ResearchQueryService
from ..ingestion.parsers import BatchIngestor
from ..ai.classifier import BehavioralClassifier
from ..validation.benchmark import BenchmarkEvaluator
from ..validation.reviewer import HumanReviewManager
from ..pipeline.incremental import IncrementalPipeline


app = FastAPI(
    title="Nykaa AI Discovery Platform API",
    description="High-performance backend for consumer discovery analytics, opportunity prioritization, RAG queries, and validation.",
    version="1.0.0"
)

# CORS middleware for interactive dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize service singletons
db = FeedbackDatabase()
analytics_aggregator = AnalyticsAggregator(db)
opportunity_scorer = OpportunityScorer(db)
query_service = ResearchQueryService(db=db)
benchmark_evaluator = BenchmarkEvaluator()
review_manager = HumanReviewManager(db)
incremental_pipeline = IncrementalPipeline(db=db, search_index=query_service.search_index)


def clean_dataframe_records(df) -> List[Dict[str, Any]]:
    """Convert pandas/duckdb dataframe with numpy ndarrays into native Python types for JSON serialization."""
    records = df.to_dict(orient="records")
    clean_list = []
    for r in records:
        clean_row = {}
        for k, v in r.items():
            if hasattr(v, "tolist"):
                clean_row[k] = v.tolist()
            elif isinstance(v, list):
                clean_row[k] = [item.tolist() if hasattr(item, "tolist") else item for item in v]
            else:
                clean_row[k] = v
        clean_list.append(clean_row)
    return clean_list


# --- Request/Response Models ---

class WeightOverrides(BaseModel):
    purchase_relevance: Optional[float] = Field(None, ge=1.0, le=5.0)
    segment_impact: Optional[float] = Field(None, ge=1.0, le=5.0)
    solvability: Optional[float] = Field(None, ge=1.0, le=5.0)


class AskQueryRequest(BaseModel):
    query: str
    category: Optional[str] = None
    theme: Optional[str] = None
    top_k: int = 5


class HumanOverrideRequest(BaseModel):
    record_id: str
    theme: Optional[str] = None
    wishlist_intent: Optional[str] = None
    purchase_blocker: Optional[List[str]] = None
    information_gap: Optional[List[str]] = None
    notes: Optional[str] = None


# --- API Routes ---

@app.get("/api/overview")
def get_overview(category: Optional[str] = None):
    """Fetch high-level overview metrics."""
    return analytics_aggregator.get_overview_metrics(category_filter=category)


@app.get("/api/analytics/themes")
def get_themes(category: Optional[str] = None):
    """Fetch primary behavioral theme distribution."""
    return analytics_aggregator.get_theme_distribution(category_filter=category)


@app.get("/api/analytics/blockers")
def get_blockers(category: Optional[str] = None):
    """Fetch ranked purchase blockers matrix."""
    return analytics_aggregator.get_blocker_matrix(category_filter=category)


@app.get("/api/analytics/gaps")
def get_information_gaps(category: Optional[str] = None):
    """Fetch information gaps analysis."""
    return analytics_aggregator.get_information_gaps(category_filter=category)


@app.get("/api/analytics/categories")
def get_categories_breakdown():
    """Fetch multi-theme breakdown across product categories."""
    return analytics_aggregator.get_category_breakdown_matrix()


@app.get("/api/analytics/channels")
def get_channel_patterns():
    """Fetch research channels vs comparison behavior patterns."""
    return analytics_aggregator.get_channel_and_comparison_patterns()


@app.get("/api/analytics/triggers")
def get_decision_triggers():
    """Fetch top decision trigger catalysts."""
    return analytics_aggregator.get_decision_triggers_distribution()


@app.get("/api/opportunities")
def get_opportunities(
    shade_rel: float = Query(4.8, ge=1.0, le=5.0),
    shade_imp: float = Query(4.5, ge=1.0, le=5.0),
    shade_sol: float = Query(4.5, ge=1.0, le=5.0),
    price_rel: float = Query(4.2, ge=1.0, le=5.0),
    price_imp: float = Query(4.8, ge=1.0, le=5.0),
    price_sol: float = Query(4.0, ge=1.0, le=5.0),
    suit_rel: float = Query(4.6, ge=1.0, le=5.0),
    suit_imp: float = Query(4.3, ge=1.0, le=5.0),
    suit_sol: float = Query(4.2, ge=1.0, le=5.0),
    qual_rel: float = Query(4.4, ge=1.0, le=5.0),
    qual_imp: float = Query(4.0, ge=1.0, le=5.0),
    qual_sol: float = Query(3.8, ge=1.0, le=5.0),
    comp_rel: float = Query(3.9, ge=1.0, le=5.0),
    comp_imp: float = Query(4.1, ge=1.0, le=5.0),
    comp_sol: float = Query(4.0, ge=1.0, le=5.0),
    decay_rel: float = Query(3.5, ge=1.0, le=5.0),
    decay_imp: float = Query(3.8, ge=1.0, le=5.0),
    decay_sol: float = Query(4.6, ge=1.0, le=5.0),
):
    """Compute deterministic opportunity priority scores with dynamic sensitivity weights."""
    custom_weights = {
        "SHADE_CONFIDENCE": {"purchase_relevance": shade_rel, "segment_impact": shade_imp, "solvability": shade_sol},
        "PRICE_VALUE": {"purchase_relevance": price_rel, "segment_impact": price_imp, "solvability": price_sol},
        "SUITABILITY": {"purchase_relevance": suit_rel, "segment_impact": suit_imp, "solvability": suit_sol},
        "QUALITY_TRUST": {"purchase_relevance": qual_rel, "segment_impact": qual_imp, "solvability": qual_sol},
        "COMPARISON": {"purchase_relevance": comp_rel, "segment_impact": comp_imp, "solvability": comp_sol},
        "INTENT_DECAY": {"purchase_relevance": decay_rel, "segment_impact": decay_imp, "solvability": decay_sol},
    }
    return opportunity_scorer.compute_opportunity_rankings(custom_weights=custom_weights)


@app.get("/api/evidence")
def get_evidence_records(
    category: Optional[str] = None,
    theme: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Fetch raw feedback records joined with behavioral classifications."""
    conn = db.get_connection()
    try:
        conditions = []
        params = []
        if category and category != "ALL":
            conditions.append("r.product_category = ?")
            params.append(category)
        if theme and theme != "ALL":
            conditions.append("b.theme = ?")
            params.append(theme)
        if source and source != "ALL":
            conditions.append("r.source = ?")
            params.append(source)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_query = f"""
            SELECT COUNT(*)
            FROM raw_feedback r
            JOIN behavioral_records b ON r.record_id = b.record_id
            {where_clause};
        """
        total_matching = conn.execute(count_query, params).fetchone()[0]

        data_query = f"""
            SELECT r.record_id, r.source, r.source_url, r.date, r.raw_text, r.product_category,
                   b.wishlist_intent, b.purchase_blocker, b.information_gap, b.comparison_behavior,
                   b.comparison_type, b.external_research, b.decision_trigger, b.sentiment,
                   b.confidence_score, b.verbatim_evidence, b.theme, b.segment, b.status,
                   b.model_version, b.analyzed_at
            FROM raw_feedback r
            JOIN behavioral_records b ON r.record_id = b.record_id
            {where_clause}
            ORDER BY r.record_id
            LIMIT {limit} OFFSET {offset};
        """
        df = conn.execute(data_query, params).fetchdf()
        records = clean_dataframe_records(df)

        return {
            "total": int(total_matching),
            "limit": int(limit),
            "offset": int(offset),
            "records": records,
        }
    finally:
        conn.close()


@app.post("/api/query/ask")
def ask_question(req: AskQueryRequest):
    """Execute RAG question answering."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return query_service.ask(query=req.query, category=req.category, theme=req.theme, top_k=req.top_k)


# --- Incremental Ingestion & Audit Routes ---

@app.post("/api/ingest/upload")
@app.post("/api/ingest/incremental")
async def upload_incremental_dataset(file: UploadFile = File(...)):
    """
    Incrementally ingest and classify a new dataset file (CSV, XLSX, JSON)
    without reprocessing historical records.
    """
    os.makedirs("data/uploads", exist_ok=True)
    temp_path = f"data/uploads/{file.filename}"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        report = incremental_pipeline.ingest_and_process(temp_path)
        return {
            "filename": file.filename,
            "audit_report": report.dict(),
            "status": "SUCCESS"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


@app.post("/api/ingest/retry-failed")
def retry_failed_records():
    """Retry any previously failed records without duplicating data."""
    report = incremental_pipeline.retry_failed_records()
    return {"status": "SUCCESS", "audit_report": report.dict()}


@app.get("/api/pipeline/audit")
def get_pipeline_audit_logs(limit: int = Query(20, ge=1, le=100)):
    """Retrieve recent batch ingestion audit logs."""
    return db.get_audit_logs(limit=limit)


@app.get("/api/records/{record_id}/lineage")
def get_record_lineage(record_id: str):
    """Retrieve full audit lineage and traceability details for a single record."""
    info = db.get_record_audit_info(record_id)
    if not info:
        raise HTTPException(status_code=404, detail="Record not found")
    return info


# --- Validation & Human Review Routes ---

@app.get("/api/validation/benchmark-report")
def get_benchmark_report():
    """Run gold-standard 100-sample benchmark evaluation and return precision/recall/kappa."""
    return benchmark_evaluator.run_benchmark()


@app.get("/api/validation/review-queue")
def get_review_queue(threshold: float = Query(0.70, ge=0.0, le=1.0)):
    """Fetch records with confidence below threshold for human inspection."""
    return review_manager.get_review_queue(min_confidence_threshold=threshold)


@app.post("/api/validation/override")
def override_classification(req: HumanOverrideRequest):
    """Submit human review approval or override."""
    success = review_manager.approve_or_override_classification(
        record_id=req.record_id,
        theme=req.theme,
        wishlist_intent=req.wishlist_intent,
        purchase_blocker=req.purchase_blocker,
        information_gap=req.information_gap,
        notes=req.notes
    )
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "SUCCESS", "record_id": req.record_id, "approved": True}


# --- Static Files & SPA Route ---

static_dir = os.path.join(os.path.dirname(__file__), "..", "ui", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_dashboard():
        return FileResponse(os.path.join(static_dir, "index.html"))
