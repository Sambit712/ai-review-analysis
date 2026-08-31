# Context: AI Discovery Engine & Data Pipeline for Beauty Shopping

> **Source:** [`Docs/problem-statement.txt`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/Docs/problem-statement.txt) | **Incremental Ingestion Spec:** [`Docs/Update.txt`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/Docs/Update.txt)

---

## 1. Executive Summary & Core Objective

Build an **AI-powered discovery engine and continuous data pipeline** that ingests unstructured public user feedback about online beauty shopping and converts it into **structured, searchable, and quantifiable evidence** regarding:
- **Wishlist-to-purchase blockers:** Why users wishlist beauty products but abandon or delay purchase.
- **Alternative behaviors & external research:** What information users seek outside the platform and where they go (e.g., Reddit, YouTube).
- **Information gaps & decision triggers:** What missing details prevent checkout and what would unlock confidence.
- **Opportunity identification:** Unmet needs scored by business relevance, solvability, and volume.

> **Core Principle:** The system is **not** a simple sentiment analyzer or review summarizer. It must identify **behavioral patterns, decision barriers, user segments, and opportunity areas** while maintaining complete **evidence traceability** down to the raw user quote.

---

## 2. System Architecture & End-to-End Data Flow

The Discovery Engine operates as a **continuous incremental research system**: every new piece of feedback becomes new evidence in the knowledge base **without requiring the entire historical dataset to be reprocessed**.

```text
Multiple Feedback Sources (Reddit, YouTube, App Reviews, Surveys, Files, APIs)
          ↓
     Ingestion Layer (Batch CSV/XLSX/JSON & API Uploads)
          ↓
 Schema Normalization & Composite Deduplication (Record ID + Hash Check)
     ↙                                    ↘
[Duplicate / Existing]              [Genuinely New]
     ↓                                    ↓
  Reject & Audit Log               Store Raw Feedback (Status: NEW)
                                          ↓
                                    AI Behavioral Classifier
                                    (Groq LLaMA-3.3-70B / Fallback)
                                          ↓
                                    Store Enriched Behavioral Record
                                    (Status: PROCESSED / REQUIRES_REVIEW / FAILED)
                                          ↓
                                    Programmatic Insight Recalculation
                                    (Frequencies, Themes, Opportunity Scores)
                                          ↓
                                    Search Index Refresh (In-Memory BM25)
                                          ↓
                                    Discovery Dashboard UI & Research Query RAG
```

---

## 3. Continuous Incremental Ingestion & Lifecycle Management

Per the incremental pipeline requirements ([`Docs/Update.txt`](file:///c:/Users/kumar/Desktop/New%20folder%20(3)/Docs/Update.txt)), the engine adheres to five foundational lifecycle guarantees:

### A. Lifecycle State Machine
Each record transitions through explicit processing states:
- `NEW`: Ingested into raw database, awaiting behavioral AI classification.
- `PROCESSING`: Currently dispatched to the AI classification worker pool.
- `PROCESSED`: Successfully classified with high confidence ($\ge 0.70$) and indexed.
- `REQUIRES_REVIEW` (or `NEEDS_REVIEW`): Classified with low confidence ($< 0.70$), flagged for human QA inspection.
- `FAILED`: Classification failed due to transient API/network error, contained and eligible for retry.
- `HUMAN_APPROVED`: Human reviewer audited and validated/overrode classification.

### B. Stable Deduplication & Zero Historical Reprocessing
- **Deduplication Strategy**: Fast $O(1)$ set lookup against existing `record_id` and composite text hash (`source + source_url + normalized_text + date`).
- **Zero Reprocessing Guarantee**: If the database contains 10,000 historical records and 300 new records arrive, **only the 300 new records are sent to the AI model**. Historical records are never re-sent to the LLM, dramatically cutting API cost and processing latency.

### C. Historical Stability & Immutability
Previously processed records remain locked and immutable. Historical classifications do not shift when new feedback arrives, ensuring discovery trends remain stable unless an explicit taxonomy re-run is triggered.

### D. Full Lineage & Traceability
Every insight, theme, and aggregate frequency is traceable back to:
- Raw feedback verbatim text
- Source platform and origin URL
- AI model version (e.g., `llama-3.3-70b-versatile`)
- UTC timestamps (`ingested_at`, `analyzed_at`)
- Classification confidence score ($0.0 - 1.0$)
- Ingestion batch ID and audit log report

### E. Failure Containment & Safe Retries
If LLM processing encounters rate limits or network failures during a batch:
- Raw records remain safely persisted in the database.
- Failed records are tagged with status `FAILED` and capture the exact error message.
- Successfully processed records remain live and searchable.
- Failed records can be retried via CLI or API without creating duplicate entries or reprocessing successful records.

---

## 4. Analytical Capabilities & Quantification

### A. Core Behavioral Taxonomy
1. **Wishlist Intent**: `GENUINE_PURCHASE_INTENT`, `BOOKMARK`, `COMPARISON`, `WAITING_FOR_RIGHT_TIME`, `WAITING_FOR_BETTER_VALUE`, `INSPIRATION`, `FUTURE_NEED`, `UNCERTAIN`, `OTHER`.
2. **Purchase Blocker**: `SHADE`, `PRICE_VALUE`, `PRICE`, `FINISH`, `SUITABILITY`, `QUALITY`, `QUALITY_TRUST`, `REVIEWS_SOCIAL_PROOF`, `COMPARISON`, `ALTERNATIVE_FOUND`, `FORGOT`, `TIMING_OCCASION`, `AVAILABILITY`, `RETURNS`, `TRUST`, `NO_NEED`, `SIZE_FORMAT`, `INGREDIENT_SAFETY`, `PACKAGING`, `PERFORMANCE_DOUBT`, `OTHER`.
3. **Information Gap**: `SHADE_CONFIDENCE`, `PRODUCT_QUALITY`, `PERFORMANCE`, `SUITABILITY`, `INGREDIENTS`, `PRICE_VALUE`, `REVIEWS`, `RETURN_POLICY`, `DELIVERY`, `SOCIAL_PROOF`, `COMPARISON`, `OTHER`.
4. **Comparison Behavior**: Boolean flag + `[OTHER_BRAND, SAME_PRODUCT_OTHER_PLATFORM, SIMILAR_PRODUCT, PRICE, OFFER, DELIVERY, RETURNS, QUALITY, REVIEWS, OTHER, NONE]`.
5. **External Research**: `[NONE, GOOGLE, YOUTUBE, INSTAGRAM, REDDIT, OTHER_MARKETPLACE, OFFLINE_STORE, FRIENDS, OTHER]`.
6. **Decision Trigger**: `[LOWER_PRICE, BETTER_VALUE, BETTER_REVIEWS, SHADE_CONFIRMATION, SUITABILITY_CONFIDENCE, PRODUCT_DEMO, BETTER_ALTERNATIVE, AVAILABILITY, OCCASION, REPLENISHMENT, SOCIAL_PROOF, OTHER]`.

### B. Deterministic Opportunity Scoring Formula
To avoid hallucinated metrics, all scores are computed strictly by mathematical formula:

$$\text{Opportunity Score} = \left(\frac{\text{Theme Count}}{\text{Total Analyzed Records}}\right) \times \text{Purchase Relevance (1--5)} \times \text{Segment Impact (1--5)} \times \text{Solvability (1--5)} \times 10$$

---

## 5. User Interfaces & Discovery Experience

1. **Executive Overview Dashboard**: High-level KPIs, total records, active blocker volume, and confidence distributions.
2. **Problem & Blocker Matrix**: Deep dive into purchase blockers and information gaps by product category.
3. **Category Breakdown**: Cross-tabulation of makeup, skincare, haircare, and fragrance blockers.
4. **Evidence & Lineage Explorer**: Searchable verbatim quotes with source links, timestamps, and model version audit details.
5. **Opportunity Prioritization**: Ranked table of commercial opportunities with editable scoring weights.
6. **AI Research Assistant (RAG)**: Natural-language query interface returning synthesized insights backed by direct record citations.
7. **Validation & QA Console**: Human-in-the-loop review interface with inter-annotator agreement (Cohen's Kappa $\kappa$) and benchmark scoring.
