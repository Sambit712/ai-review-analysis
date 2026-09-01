"""
Incremental Review Ingestion & AI Analysis Pipeline Orchestrator.
Enforces zero reprocessing of historical records, deterministic deduplication,
traceability, failure recovery, and automatic insight recalculation.
"""

import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..models.schema import (
    NormalizedRecord,
    BehavioralRecord,
    ProcessingStatus,
    IngestionAuditReport,
)
from ..ingestion.parsers import BatchIngestor
from ..storage.db import FeedbackDatabase
from ..ai.classifier import BehavioralClassifier
from ..analytics.opportunity_scorer import OpportunityScorer
from ..query.indexer import ResearchSearchIndex


def to_dict_safe(model_obj) -> Dict[str, Any]:
    """Safely convert Pydantic model to dictionary across V1 and V2."""
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()
    elif hasattr(model_obj, "dict"):
        return model_obj.dict()
    return dict(model_obj)


class IncrementalPipeline:
    """
    Continuous Incremental Pipeline for feedback ingestion and behavioral analysis.
    Guarantees:
    - Zero reprocessing of historical records (preserves historical classifications and saves LLM costs).
    - Stable deduplication across record_id and content hash.
    - Full traceability (raw text, model version, timestamp, confidence score, source URL).
    - Immediate programmatic insight recalculation (opportunity scores & search index).
    - Failure isolation and recovery.
    """

    def __init__(
        self,
        db: Optional[FeedbackDatabase] = None,
        classifier: Optional[BehavioralClassifier] = None,
        search_index: Optional[ResearchSearchIndex] = None,
    ):
        self.db = db or FeedbackDatabase()
        self.classifier = classifier or BehavioralClassifier()
        self.ingestor = BatchIngestor()
        self.scorer = OpportunityScorer(self.db)
        self.search_index = search_index or ResearchSearchIndex(self.db)

    def ingest_and_process(
        self,
        source: Union[str, List[Dict[str, Any]]],
        max_workers: int = 5,
        recalculate_insights: bool = True,
    ) -> IngestionAuditReport:
        """
        Execute the full incremental lifecycle on a new file or list of raw records.
        """
        start_time = time.time()
        batch_id = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Step 1: Parse and normalize incoming records
        if isinstance(source, str):
            normalized_candidates = self.ingestor.ingest_file(source)
        else:
            normalized_candidates = self.ingestor.ingest_dict_list(source)

        total_received = len(normalized_candidates)
        if total_received == 0:
            duration_ms = (time.time() - start_time) * 1000
            return IngestionAuditReport(
                batch_id=batch_id,
                total_received=0,
                duplicates_rejected=0,
                new_records_ingested=0,
                classified_count=0,
                flagged_review_count=0,
                failed_count=0,
                duration_ms=round(duration_ms, 2),
                timestamp=datetime.utcnow().isoformat(),
                insights_recalculated=False,
            )

        # Step 2: Deduplication against existing database records
        existing_ids = self.db.get_existing_record_ids()
        existing_hashes = self.db.get_existing_hashes()

        genuinely_new_records: List[NormalizedRecord] = []
        duplicates_count = 0

        for r in normalized_candidates:
            if r.record_id in existing_ids or r.text_hash in existing_hashes:
                duplicates_count += 1
            else:
                r.status = ProcessingStatus.NEW
                genuinely_new_records.append(r)
                # Add to local tracking sets to prevent duplicates within the same batch
                existing_ids.add(r.record_id)
                existing_hashes.add(r.text_hash)

        # Step 3: Persist genuinely new raw records into DuckDB
        new_ingested = self.db.insert_normalized_records(genuinely_new_records)

        # Step 4: Incremental AI Behavioral Processing (Only new records!)
        classified_records: List[BehavioralRecord] = []
        flagged_review_count = 0
        failed_count = 0

        if genuinely_new_records:
            records_to_process = [to_dict_safe(r) for r in genuinely_new_records]

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_rec = {
                    executor.submit(self._classify_safe, rec): rec
                    for rec in records_to_process
                }
                for future in as_completed(future_to_rec):
                    b_rec = future.result()
                    classified_records.append(b_rec)
                    if b_rec.status == ProcessingStatus.REQUIRES_REVIEW:
                        flagged_review_count += 1
                    elif b_rec.status == ProcessingStatus.FAILED:
                        failed_count += 1

            # Step 5: Batch persist AI enriched records
            self.db.save_behavioral_records(classified_records)

        # Step 6: Recalculate Aggregate Insights & Update Search Index
        if recalculate_insights and genuinely_new_records:
            self.scorer.compute_opportunity_rankings()
            self.search_index.build_index()

        duration_ms = (time.time() - start_time) * 1000
        audit_report = IngestionAuditReport(
            batch_id=batch_id,
            total_received=total_received,
            duplicates_rejected=duplicates_count,
            new_records_ingested=new_ingested,
            classified_count=len(classified_records) - failed_count,
            flagged_review_count=flagged_review_count,
            failed_count=failed_count,
            duration_ms=round(duration_ms, 2),
            timestamp=datetime.utcnow().isoformat(),
            insights_recalculated=recalculate_insights and (new_ingested > 0),
        )

        # Log audit report to DuckDB
        self.db.log_audit_batch(to_dict_safe(audit_report))

        return audit_report

    def _classify_safe(self, raw_record: Dict[str, Any]) -> BehavioralRecord:
        """Safely classify a single record with failure containment."""
        rec_id = str(raw_record.get("record_id"))
        try:
            return self.classifier.classify_raw_dict(raw_record)
        except Exception as exc:
            # Failure recovery: store failed record state
            return BehavioralRecord(
                record_id=rec_id,
                status=ProcessingStatus.FAILED,
                error_message=str(exc),
                verbatim_evidence=raw_record.get("raw_text", "")[:100],
                confidence_score=0.0,
                model_version="error-fallback",
            )

    def retry_failed_records(self, max_workers: int = 5) -> IngestionAuditReport:
        """
        Retry previously failed records without duplicating existing data.
        """
        start_time = time.time()
        batch_id = f"RETRY_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        failed_records = self.db.get_failed_records()
        if not failed_records:
            return IngestionAuditReport(
                batch_id=batch_id,
                total_received=0,
                duplicates_rejected=0,
                new_records_ingested=0,
                classified_count=0,
                flagged_review_count=0,
                failed_count=0,
                duration_ms=round((time.time() - start_time) * 1000, 2),
                timestamp=datetime.utcnow().isoformat(),
                insights_recalculated=False,
            )

        classified_records: List[BehavioralRecord] = []
        flagged_review = 0
        still_failed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_rec = {
                executor.submit(self._classify_safe, rec): rec
                for rec in failed_records
            }
            for future in as_completed(future_to_rec):
                b_rec = future.result()
                classified_records.append(b_rec)
                if b_rec.status == ProcessingStatus.REQUIRES_REVIEW:
                    flagged_review += 1
                elif b_rec.status == ProcessingStatus.FAILED:
                    still_failed += 1

        self.db.save_behavioral_records(classified_records)
        self.scorer.compute_opportunity_rankings()
        self.search_index.build_index()

        duration_ms = (time.time() - start_time) * 1000
        audit_report = IngestionAuditReport(
            batch_id=batch_id,
            total_received=len(failed_records),
            duplicates_rejected=0,
            new_records_ingested=0,
            classified_count=len(classified_records) - still_failed,
            flagged_review_count=flagged_review,
            failed_count=still_failed,
            duration_ms=round(duration_ms, 2),
            timestamp=datetime.utcnow().isoformat(),
            insights_recalculated=True,
        )

        self.db.log_audit_batch(to_dict_safe(audit_report))
        return audit_report

    def delete_records(
        self,
        record_ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        recalculate_insights: bool = True,
    ) -> Dict[str, Any]:
        """
        Delete a set of records from storage, re-index search, and recalculate insights.
        """
        result = self.db.delete_records(
            record_ids=record_ids,
            category=category,
            source=source,
            status=status,
        )

        insights_updated = False
        if result.get("deleted_count", 0) > 0 and recalculate_insights:
            try:
                self.scorer.compute_opportunity_rankings()
            except Exception:
                pass
            try:
                self.search_index.build_index()
            except Exception:
                pass
            insights_updated = True

        result["insights_recalculated"] = insights_updated
        return result

