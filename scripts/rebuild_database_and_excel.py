"""
Rebuild feedback.duckdb database and synchronize Excel files with new datasets:
- Docs/nykaa_ai_discovery_database_statements.xlsx (Base 2,916 statements)
- data/uploads/nykaa_ai_discovery_database_100_new_statements.xlsx (Incremental 110 statements)
"""

import os
import duckdb
import pandas as pd
import openpyxl
from datetime import datetime
from src.storage.db import FeedbackDatabase
from src.pipeline.incremental import IncrementalPipeline
from src.ingestion.parsers import BatchIngestor
from src.ai.groq_client import GroqClient
from src.ai.classifier import BehavioralClassifier
from src.analytics.opportunity_scorer import OpportunityScorer
from src.query.indexer import ResearchSearchIndex


def rebuild_all():
    db_path = "data/raw_db/feedback.duckdb"
    
    # 1. Clear existing database file to start fresh with the new datasets
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[*] Cleared old {db_path}")

    db = FeedbackDatabase(db_path=db_path)
    search_index = ResearchSearchIndex(db=db)
    client = GroqClient(api_key="")  # Fast rule-based taxonomy classifier for 3,000+ statements
    classifier = BehavioralClassifier(groq_client=client)
    pipeline = IncrementalPipeline(db=db, classifier=classifier, search_index=search_index)

    # 2. Ingest primary base dataset: Docs/nykaa_ai_discovery_database_statements.xlsx
    base_file = "Docs/nykaa_ai_discovery_database_statements.xlsx"
    print(f"\n[*] Ingesting base statements dataset: {base_file}...")
    base_report = pipeline.ingest_and_process(base_file, max_workers=10, recalculate_insights=True)
    print("=== BASE DATASET INGESTION REPORT ===")
    print(f"Batch ID:                  {base_report.batch_id}")
    print(f"Total Records Received:    {base_report.total_received}")
    print(f"Duplicates Rejected:       {base_report.duplicates_rejected}")
    print(f"New Records Ingested:      {base_report.new_records_ingested}")
    print(f"AI Records Classified:     {base_report.classified_count}")
    print(f"Flagged for Human Review:  {base_report.flagged_review_count}")
    print(f"Failed Records:            {base_report.failed_count}")
    print(f"Processing Duration:       {base_report.duration_ms:.2f} ms")

    # 3. Ingest incremental dataset: data/uploads/nykaa_ai_discovery_database_100_new_statements.xlsx
    inc_file = "data/uploads/nykaa_ai_discovery_database_100_new_statements.xlsx"
    print(f"\n[*] Ingesting incremental dataset: {inc_file}...")
    inc_report = pipeline.ingest_and_process(inc_file, max_workers=10, recalculate_insights=True)
    print("=== INCREMENTAL DATASET INGESTION REPORT ===")
    print(f"Batch ID:                  {inc_report.batch_id}")
    print(f"Total Records Received:    {inc_report.total_received}")
    print(f"Duplicates Rejected:       {inc_report.duplicates_rejected}")
    print(f"New Records Ingested:      {inc_report.new_records_ingested}")
    print(f"AI Records Classified:     {inc_report.classified_count}")
    print(f"Flagged for Human Review:  {inc_report.flagged_review_count}")
    print(f"Failed Records:            {inc_report.failed_count}")
    print(f"Processing Duration:       {inc_report.duration_ms:.2f} ms")

    # 4. Print overall database stats
    stats = db.get_stats_summary()
    print("\n" + "=" * 60)
    print("=== DATABASE OVERALL SUMMARY METRICS ===")
    print("=" * 60)
    print(f"Total Raw Records:        {stats['total_raw_records']}")
    print(f"Total Canonical Records:  {stats['total_canonical_records']}")
    print(f"Total Duplicate Records:  {stats['total_duplicate_records']}")
    print(f"Total Analyzed Records:   {stats['total_analyzed_records']}")
    print("\nCategory Breakdown:")
    for cat, cnt in stats['category_breakdown'].items():
        print(f"  {cat:<25} : {cnt}")
    print("\nSource Breakdown:")
    for src, cnt in stats['source_breakdown'].items():
        print(f"  {src:<25} : {cnt}")
    print("=" * 60 + "\n")

    # 5. Synchronize Excel files (populate AI_Classification & Opportunity_Scoring sheets)
    sync_excel_sheets(db, base_file)
    sync_excel_sheets(db, inc_file)
    print("[OK] Rebuild and Excel synchronization completed successfully!")


def sync_excel_sheets(db: FeedbackDatabase, excel_path: str):
    print(f"[*] Synchronizing Excel file: {excel_path}...", flush=True)
    conn = db.get_connection()
    try:
        # Load all behavioral records in one single query
        all_enriched = conn.execute("""
            SELECT r.record_id, r.raw_text, r.text_hash,
                   b.wishlist_intent, b.purchase_blocker, b.information_gap,
                   b.comparison_behavior, b.comparison_type, b.external_research,
                   b.decision_trigger, b.sentiment, b.confidence_score, b.verbatim_evidence,
                   b.theme, b.segment
            FROM raw_feedback r
            JOIN behavioral_records b ON r.record_id = b.record_id;
        """).fetchdf()

        # Build fast lookup map by text_hash, raw_text, and record_id
        from src.ingestion.normalizer import compute_text_hash
        record_map = {}
        for _, r in all_enriched.iterrows():
            record_map[str(r["record_id"])] = r
            record_map[str(r["text_hash"])] = r
            record_map[str(r["raw_text"])] = r

        # Load Raw feedback from Excel to match rows
        df_raw = pd.read_excel(excel_path, sheet_name="Feedback_Raw")
        
        ai_rows = []
        classifier = BehavioralClassifier(groq_client=GroqClient(api_key=""))

        for idx, row in df_raw.iterrows():
            text = str(row.get("text", ""))
            category = str(row.get("product_category", "BEAUTY"))
            source = str(row.get("source", "FEEDBACK"))
            rec_id = str(row.get("record_id", idx + 1))
            t_hash = compute_text_hash(text)

            # Match in lookup map
            db_row = None
            if rec_id in record_map:
                db_row = record_map[rec_id]
            elif t_hash in record_map:
                db_row = record_map[t_hash]
            elif text in record_map:
                db_row = record_map[text]

            if db_row is not None:
                w_intent = db_row["wishlist_intent"]
                p_blocker = db_row["purchase_blocker"]
                info_gap = db_row["information_gap"]
                comp_beh = db_row["comparison_behavior"]
                comp_type = db_row["comparison_type"]
                ext_res = db_row["external_research"]
                dec_trig = db_row["decision_trigger"]
                sent = db_row["sentiment"]
                conf = db_row["confidence_score"]
                verb = db_row["verbatim_evidence"]
                theme = db_row["theme"]
                seg = db_row["segment"]

                p_blocker_str = ", ".join(p_blocker) if isinstance(p_blocker, list) else str(p_blocker)
                info_gap_str = ", ".join(info_gap) if isinstance(info_gap, list) else str(info_gap)
                comp_type_str = ", ".join(comp_type) if isinstance(comp_type, list) else str(comp_type)
                ext_res_str = ", ".join(ext_res) if isinstance(ext_res, list) else str(ext_res)
                dec_trig_str = ", ".join(dec_trig) if isinstance(dec_trig, list) else str(dec_trig)
            else:
                b_rec = classifier.classify_text(text, category, source, rec_id)
                w_intent = b_rec.wishlist_intent.value if b_rec.wishlist_intent else None
                p_blocker_str = ", ".join([b.value if hasattr(b, 'value') else str(b) for b in b_rec.purchase_blocker])
                info_gap_str = ", ".join([g.value if hasattr(g, 'value') else str(g) for g in b_rec.information_gap])
                comp_beh = b_rec.comparison_behavior
                comp_type_str = ", ".join([c.value if hasattr(c, 'value') else str(c) for c in b_rec.comparison_type])
                ext_res_str = ", ".join([e.value if hasattr(e, 'value') else str(e) for e in b_rec.external_research])
                dec_trig_str = ", ".join([t.value if hasattr(t, 'value') else str(t) for t in b_rec.decision_trigger])
                sent = b_rec.sentiment.value if b_rec.sentiment else None
                conf = b_rec.confidence_score
                verb = b_rec.verbatim_evidence
                theme = b_rec.theme
                seg = b_rec.segment

            ai_rows.append({
                "record_id": rec_id,
                "source": source,
                "text": text,
                "category": category,
                "wishlist_intent": w_intent,
                "purchase_blocker": p_blocker_str,
                "information_gap": info_gap_str,
                "comparison_behavior": comp_beh,
                "comparison_type": comp_type_str,
                "external_research": ext_res_str,
                "decision_trigger": dec_trig_str,
                "sentiment": sent,
                "confidence": conf,
                "evidence": verb,
                "theme": theme,
                "segment": seg,
                "opportunity_relevance": theme,
            })

        df_ai_new = pd.DataFrame(ai_rows)

        # Get Opportunity Scores
        opp_rows = conn.execute("""
            SELECT opportunity_theme, frequency_count, frequency_pct,
                   purchase_relevance_1_5, segment_impact_1_5, solvability_1_5,
                   opportunity_score
            FROM opportunity_scores
            ORDER BY opportunity_score DESC;
        """).fetchdf()

        # Update Excel workbook preserving sheets
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df_ai_new.to_excel(writer, sheet_name="AI_Classification", index=False)
            opp_rows.to_excel(writer, sheet_name="Opportunity_Scoring", index=False)

        print(f"  [OK] Updated AI_Classification ({len(df_ai_new)} rows) and Opportunity_Scoring ({len(opp_rows)} rows) in {excel_path}", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    rebuild_all()
