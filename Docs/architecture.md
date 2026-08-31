# System Architecture: AI Discovery Engine & Continuous Incremental Pipeline

> **Reference Context:** [`context.md`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/context.md) | **Problem Statement:** [`Docs/problem-statement.txt`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/Docs/problem-statement.txt) | **Incremental Ingestion Spec:** [`Docs/Update.txt`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/Docs/Update.txt)

---

## 1. Executive Summary & Design Principles

The **AI Discovery Engine** is a high-throughput, evidence-traceable intelligence pipeline designed to continuously ingest unstructured consumer feedback across public channels (Reddit, YouTube, App Stores, Communities, Reviews, Surveys) and transform it into structured, quantifiable behavioural insights regarding **beauty shopping and wishlist abandonment**.

### Core Architecture Tenets
1. **Continuous Incremental Ingestion (Zero Reprocessing)**:
   - Newly ingested batches are deduplicated in $O(1)$ time against existing IDs and composite content hashes (`source + URL + normalized text + date`).
   - Only genuinely new records are sent to the AI classifier. Previously processed historical records remain locked, saving LLM tokens and maintaining historical stability.
2. **Strict Separation of AI vs. Deterministic Computing**:
   - **AI Layer** performs semantic extraction, qualitative classification, intent identification, and natural-language synthesis.
   - **Deterministic Layer** handles all statistical counts, aggregations, frequency calculations, segment slicing, deduplication, and mathematical opportunity scoring to prevent hallucinated numbers.
3. **Immutable Traceability & Audit Lineage**:
   - Every metric, cluster, and insight links directly to supporting verbatim evidence quotes, confidence scores, source URLs, model versions, and batch execution logs.
4. **Resilient Failure Recovery & Containment**:
   - Classification failures are contained with explicit `FAILED` status and captured error messages without losing raw data or duplicating records upon retry.

---

## 2. High-Level Architecture & Incremental Pipeline Flow

```mermaid
flowchart TD
    subgraph Ingestion["1. Continuous Incremental Ingestion Layer"]
        S[New Feedback Sources: Excel, CSV, JSON, API] --> IN[Batch Ingestor & Normalizer]
        IN --> NORM[Schema Normalization & Sanitization]
        NORM --> DEDUP{Deduplication & Hash Matching}
        DEDUP -- "Exact or Content Duplicate" --> DEDUP_LOG[Reject & Preserve Existing]
        DEDUP -- "Genuinely New" --> RAW_STORE[Store Raw Feedback\nStatus: NEW]
    end

    subgraph Processing["2. Isolated AI Behavioral Classification Layer"]
        RAW_STORE --> ISOLATE[Isolated Record Dispatcher\nOnly Unprocessed / Status: NEW]
        ISOLATE --> GROQ[Groq LPU Engine\nLLaMA-3.3-70B JSON Mode]
        GROQ --> VALIDATE{Pydantic Validation & Confidence Scorer}
        VALIDATE -- "Conf >= 0.70" --> ENRICH_PROCESSED[Store Behavioral Record\nStatus: PROCESSED]
        VALIDATE -- "Conf < 0.70" --> ENRICH_REVIEW[Store Behavioral Record\nStatus: REQUIRES_REVIEW]
        VALIDATE -- "API Rate Limit / Error" --> ENRICH_FAILED[Store Failure Details\nStatus: FAILED]
    end

    subgraph Storage["3. Dual-Layer Relational Store (DuckDB)"]
        RAW_STORE --> RAW_DB[(raw_feedback Table)]
        ENRICH_PROCESSED --> ENRICH_DB[(behavioral_records Table)]
        ENRICH_REVIEW --> ENRICH_DB
        ENRICH_FAILED --> ENRICH_DB
        AUDIT_ENGINE[Batch Audit Logger] --> AUDIT_DB[(ingestion_audit_log Table)]
    end

    subgraph Analytics["4. Dynamic Programmatic Recalculation Engine"]
        ENRICH_DB --> THEME_AGG[Deterministic Theme Aggregator]
        THEME_AGG --> OPP_SCORER[Opportunity Scoring Calculator\nFrequency x Relevance x Impact x Solvability]
        OPP_SCORER --> OPP_DB[(opportunity_scores Table)]
        ENRICH_DB --> BM25_INDEX[In-Memory BM25 Search Indexer]
    end

    subgraph Discovery["5. Discovery Dashboard & Research Query Interface"]
        OPP_DB --> API[FastAPI Backend Gateway]
        BM25_INDEX --> RAG[Evidence Synthesizer & RAG Engine]
        RAG --> API
        API --> UI[Interactive Discovery Dashboard UI]
        API --> QA[Human Review & Benchmark Console]
    end
```

---

## 3. Detailed Component Breakdown

### 3.1 Ingestion & Preprocessing Layer
- **Input Handlers**:
  - `BatchIngestor`: Multi-format parsing for Excel (`.xlsx`, `.xls`), CSV, and JSON payloads with flexible column synonym resolution.
- **Deduplication Engine**:
  - Exact `record_id` match.
  - Composite SHA-256 content hash matching: `MD5(source + source_url + cleaned_text + date)`.
  - Fuzzy Jaccard token similarity ($\ge 0.85$ threshold) to catch slight comment edits.
- **Zero Historical Reprocessing Isolation**:
  - Database queries `SELECT record_id FROM raw_feedback WHERE is_duplicate = FALSE AND record_id NOT IN (SELECT record_id FROM behavioral_records WHERE status = 'PROCESSED')`.
  - Guarantees 0 redundant LLM calls on historical records.

---

### 3.2 AI Behavioral Classification Layer
- **LLM Orchestration (Groq LPU Engine)**:
  - Powered by **Groq** (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`) for ultra-low latency, high-throughput behavioral classification.
  - Native structured output enforcement using `response_format={"type": "json_object"}` and Pydantic validation schemas.
  - Concurrency pool (`ThreadPoolExecutor`) with automatic retry and error handling.
  - High-precision heuristic fallback engine for offline or rate-limited environments.
- **Classification Taxonomies**:
  - **Wishlist Intent**: `GENUINE_PURCHASE_INTENT`, `BOOKMARK`, `COMPARISON`, `WAITING_FOR_RIGHT_TIME`, `WAITING_FOR_BETTER_VALUE`, `INSPIRATION`, `FUTURE_NEED`, `UNCERTAIN`, `OTHER`.
  - **Purchase Blocker**: `SHADE`, `PRICE_VALUE`, `PRICE`, `FINISH`, `SUITABILITY`, `QUALITY`, `QUALITY_TRUST`, `REVIEWS_SOCIAL_PROOF`, `COMPARISON`, `ALTERNATIVE_FOUND`, `FORGOT`, `TIMING_OCCASION`, `AVAILABILITY`, `RETURNS`, `TRUST`, `NO_NEED`, `SIZE_FORMAT`, `INGREDIENT_SAFETY`, `PACKAGING`, `PERFORMANCE_DOUBT`, `OTHER`.
  - **Information Gap**: `SHADE_CONFIDENCE`, `PRODUCT_QUALITY`, `PERFORMANCE`, `SUITABILITY`, `INGREDIENTS`, `PRICE_VALUE`, `REVIEWS`, `RETURN_POLICY`, `DELIVERY`, `SOCIAL_PROOF`, `COMPARISON`, `OTHER`.
  - **Comparison Behavior**: Boolean flag + `[OTHER_BRAND, SAME_PRODUCT_OTHER_PLATFORM, SIMILAR_PRODUCT, PRICE, OFFER, DELIVERY, RETURNS, QUALITY, REVIEWS, OTHER, NONE]`.
  - **External Research Source**: `[NONE, GOOGLE, YOUTUBE, INSTAGRAM, REDDIT, OTHER_MARKETPLACE, OFFLINE_STORE, FRIENDS, OTHER]`.
  - **Decision Trigger**: `[LOWER_PRICE, BETTER_VALUE, BETTER_REVIEWS, SHADE_CONFIRMATION, SUITABILITY_CONFIDENCE, PRODUCT_DEMO, BETTER_ALTERNATIVE, AVAILABILITY, OCCASION, REPLENISHMENT, SOCIAL_PROOF, OTHER]`.
- **Lifecycle State Machine**:
  - `NEW`: Ingested into raw store, awaiting classification.
  - `PROCESSING`: Undergoing active inference.
  - `PROCESSED`: Successfully classified (Confidence $\ge 0.70$).
  - `REQUIRES_REVIEW` (or `NEEDS_REVIEW`): Low confidence ($< 0.70$), routed to QA console.
  - `FAILED`: Classification error captured, eligible for safe retry.
  - `HUMAN_APPROVED`: Verified or updated by human researcher.

---

### 3.3 Dynamic Programmatic Recalculation Engine
- **Deterministic Analytics Aggregator**:
  - Calculates exact theme distributions, blocker frequencies, information gap prevalence, and channel patterns in SQL.
- **Opportunity Scoring Calculator**:
  - Computes opportunity priority ranking deterministically:
    $$\text{Opportunity Score} = \left(\frac{\text{Theme Count}}{\text{Total Analyzed Records}}\right) \times \text{Relevance} \times \text{Impact} \times \text{Solvability} \times 10$$
  - Persists rankings into `opportunity_scores` table upon every incremental batch.
- **Incremental BM25 Search Indexer**:
  - Rebuilds in-memory inverted indices and BM25 term weights across raw statements, verbatim quotes, categories, and themes.

---

### 3.4 Research Query Layer (RAG)
- **Natural Language Assistant**:
  - Sub-second BM25 hybrid document retrieval filtered by category or theme.
  - Evidence synthesizer generates structured answers strictly grounded in retrieved quotes with record ID citations (`[Record #INC011]`).

---

### 3.5 Validation, QA & Audit Layer
- **100-Sample Benchmark Evaluator**:
  - Validates AI classification against expert human annotations.
  - Computes Overall Accuracy, Macro-F1, and inter-rater agreement using **Cohen's Kappa ($\kappa$)**.
- **Audit Logging**:
  - Tracks batch ID, received records, rejected duplicates, new records, classified count, review count, failed count, and execution duration in milliseconds.

---

## 4. Entity-Relationship Data Model

```mermaid
erDiagram
    RAW_FEEDBACK ||--o| BEHAVIORAL_RECORDS : "analyzed_into"
    RAW_FEEDBACK {
        string record_id PK
        string source
        string source_url
        string date
        string raw_text
        string cleaned_text
        string product_category
        string text_hash
        boolean is_duplicate
        string canonical_record_id
        string metadata_json
        string status
        timestamp ingested_at
    }

    BEHAVIORAL_RECORDS {
        string record_id PK, FK
        string wishlist_intent
        string_array purchase_blocker
        string_array information_gap
        boolean comparison_behavior
        string_array comparison_type
        string_array external_research
        string_array decision_trigger
        string sentiment
        float confidence_score
        string verbatim_evidence
        string theme
        string segment
        string status
        string model_version
        string error_message
        timestamp analyzed_at
    }

    OPPORTUNITY_SCORES {
        string opportunity_theme PK
        int frequency_count
        float frequency_pct
        float purchase_relevance_1_5
        float segment_impact_1_5
        float solvability_1_5
        float opportunity_score
        string_array evidence_quotes
        string_array affected_categories
        timestamp calculated_at
    }

    INGESTION_AUDIT_LOG {
        string batch_id PK
        int total_received
        int duplicates_rejected
        int new_records_ingested
        int classified_count
        int flagged_review_count
        int failed_count
        float duration_ms
        timestamp timestamp
    }

    VALIDATION_BENCHMARK {
        string benchmark_id PK
        string benchmark_name
        int sample_size
        float overall_accuracy
        float macro_f1
        float cohens_kappa
        string per_theme_metrics
        timestamp evaluated_at
    }
```

---

## 5. Technology Stack

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Backend & API** | **FastAPI (Python 3.11+)** | High-performance async ASGI framework with Pydantic v2 validation. |
| **Storage Engine** | **DuckDB** | Columnar embedded OLAP database providing fast aggregations and array operations. |
| **AI / LLM Engine** | **Groq SDK (`llama-3.3-70b-versatile`)** | High inference speed on LPU hardware, native JSON object mode, low cost. |
| **Retrieval Engine** | **In-Memory BM25 Indexer** | Fast tokenized search with category/theme filtering and zero external infrastructure dependencies. |
| **Frontend UI** | **Vanilla HTML5, CSS3 (Glassmorphism), Chart.js** | Lightweight, modern responsive dashboard with zero build dependencies. |
| **Evaluation Suite** | **Scikit-Learn & Pytest** | Automated Cohen's Kappa, Macro-F1 benchmark calculations, and 38/38 unit/integration test coverage. |
