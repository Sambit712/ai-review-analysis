"""
Command-line interface for the AI Discovery Engine.
"""

import argparse
import sys
import uvicorn
from src.ingestion.parsers import BatchIngestor
from src.storage.db import FeedbackDatabase
from src.ai.classifier import BehavioralClassifier
from src.ai.groq_client import GroqClient
from src.analytics.aggregator import AnalyticsAggregator
from src.analytics.opportunity_scorer import OpportunityScorer
from src.query.service import ResearchQueryService
from src.validation.benchmark import BenchmarkEvaluator
from src.validation.reviewer import HumanReviewManager
from src.pipeline.incremental import IncrementalPipeline


def main():
    parser = argparse.ArgumentParser(description="AI Discovery Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. Serve command (Dashboard Web Server)
    serve_parser = subparsers.add_parser("serve", help="Launch interactive Discovery Dashboard web server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    serve_parser.add_argument("--port", "-p", type=int, default=8000, help="Port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable live auto-reload")

    # 2. Ingest command (Standard)
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a dataset (Excel, CSV, JSON)")
    ingest_parser.add_argument("--file", "-f", required=True, help="Path to input file")
    ingest_parser.add_argument("--sheet", "-s", default=None, help="Excel sheet name (optional)")
    ingest_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 3. Incremental Ingest & AI Pipeline command
    inc_parser = subparsers.add_parser("ingest-incremental", help="Run end-to-end incremental ingestion without reprocessing history")
    inc_parser.add_argument("--file", "-f", required=True, help="Path to new feedback file (Excel, CSV, JSON)")
    inc_parser.add_argument("--workers", "-w", type=int, default=5, help="Concurrent worker threads")
    inc_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 4. Retry Failed Records command
    retry_parser = subparsers.add_parser("retry-failed", help="Retry failed classifications without data duplication")
    retry_parser.add_argument("--workers", "-w", type=int, default=5, help="Concurrent worker threads")
    retry_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 5. Classify command
    classify_parser = subparsers.add_parser("classify", help="Run AI behavioral classification on unclassified records")
    classify_parser.add_argument("--limit", "-l", type=int, default=None, help="Max records to classify")
    classify_parser.add_argument("--workers", "-w", type=int, default=5, help="Concurrent workers")
    classify_parser.add_argument("--model", "-m", default=None, help="Groq model (e.g., llama-3.3-70b-versatile)")
    classify_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 6. Analytics command
    analytics_parser = subparsers.add_parser("analytics", help="Run deterministic frequency analytics & theme aggregation")
    analytics_parser.add_argument("--category", "-c", default=None, help="Filter analytics by product category")
    analytics_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 7. Opportunities command
    opp_parser = subparsers.add_parser("opportunities", help="Calculate and rank opportunity priority scores")
    opp_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 8. Ask command (RAG Natural Language Query)
    ask_parser = subparsers.add_parser("ask", help="Ask a discovery question and receive an evidence-backed answer")
    ask_parser.add_argument("--query", "-q", required=True, help="Research question in natural language")
    ask_parser.add_argument("--category", "-c", default=None, help="Filter by product category (optional)")
    ask_parser.add_argument("--theme", "-t", default=None, help="Filter by theme (optional)")
    ask_parser.add_argument("--k", "-k", type=int, default=5, help="Number of evidence records to retrieve")
    ask_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 9. Search command (Direct Evidence Lookup)
    search_parser = subparsers.add_parser("search", help="Search raw customer evidence records")
    search_parser.add_argument("--query", "-q", required=True, help="Search terms")
    search_parser.add_argument("--category", "-c", default=None, help="Filter by category")
    search_parser.add_argument("--limit", "-n", type=int, default=5, help="Max records to return")
    search_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 10. Evaluate command (100-Sample Gold Standard Benchmark)
    eval_parser = subparsers.add_parser("evaluate", help="Run 100-sample gold standard benchmark evaluation")
    eval_parser.add_argument("--model", "-m", default=None, help="Groq model to evaluate")

    # 11. Review command (Human Review Queue)
    review_parser = subparsers.add_parser("review", help="List records flagged for human review (< 0.70 confidence)")
    review_parser.add_argument("--threshold", "-t", type=float, default=0.70, help="Confidence threshold")
    review_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 12. Audit command (Incremental Ingestion History)
    audit_parser = subparsers.add_parser("audit", help="View recent incremental batch ingestion audit logs")
    audit_parser.add_argument("--limit", "-n", type=int, default=10, help="Max audit entries")
    audit_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 13. Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database summary metrics")
    stats_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    # 14. Sample command
    sample_parser = subparsers.add_parser("sample", help="View sample classified records")
    sample_parser.add_argument("--limit", "-n", type=int, default=3, help="Number of records to display")
    sample_parser.add_argument("--db", default="data/raw_db/feedback.duckdb", help="DuckDB path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        print(f"[*] Starting Discovery Dashboard server on http://{args.host}:{args.port}")
        uvicorn.run("src.api.main:app", host=args.host, port=args.port, reload=args.reload)

    elif args.command == "ingest-incremental":
        db = FeedbackDatabase(args.db)
        pipeline = IncrementalPipeline(db=db)
        print(f"[*] Executing Incremental Pipeline for file: {args.file}...")
        report = pipeline.ingest_and_process(args.file, max_workers=args.workers)

        print("\n" + "=" * 65)
        print("=== INCREMENTAL INGESTION & ANALYSIS AUDIT REPORT ===")
        print("=" * 65)
        print(f"Batch ID:                  {report.batch_id}")
        print(f"Total Records Received:    {report.total_received}")
        print(f"Duplicates Rejected:       {report.duplicates_rejected}")
        print(f"New Records Ingested:      {report.new_records_ingested}")
        print(f"AI Records Classified:     {report.classified_count}")
        print(f"Flagged for Human Review:  {report.flagged_review_count}")
        print(f"Failed Records:            {report.failed_count}")
        print(f"Processing Duration:       {report.duration_ms:.2f} ms")
        print(f"Insights Recalculated:     {'[YES]' if report.insights_recalculated else '[NO]'}")
        print("=" * 65 + "\n")

    elif args.command == "retry-failed":
        db = FeedbackDatabase(args.db)
        pipeline = IncrementalPipeline(db=db)
        print("[*] Retrying failed records...")
        report = pipeline.retry_failed_records(max_workers=args.workers)
        print(f"[OK] Retry completed. Retried: {report.total_received} | Classified: {report.classified_count} | Failed: {report.failed_count}")

    elif args.command == "audit":
        db = FeedbackDatabase(args.db)
        logs = db.get_audit_logs(limit=args.limit)
        print("\n" + "=" * 75)
        print(f"{'Batch ID':<26} {'Received':<9} {'New':<6} {'Classified':<11} {'Review':<8} {'Time (ms)':<9}")
        print("-" * 75)
        for l in logs:
            print(f"{l['batch_id']:<26} {l['total_received']:<9} {l['new_records_ingested']:<6} {l['classified_count']:<11} {l['flagged_review_count']:<8} {l['duration_ms']:<9.1f}")
        print("=" * 75 + "\n")

    elif args.command == "ingest":
        db = FeedbackDatabase(args.db)
        ingestor = BatchIngestor()
        print(f"[*] Ingesting file: {args.file}...")
        records = ingestor.ingest_file(args.file, sheet_name=args.sheet)
        count = db.insert_normalized_records(records)
        print(f"[OK] Successfully stored {count} records in database: {args.db}")
        stats = db.get_stats_summary()
        print(f"[*] DB Stats: Total Raw: {stats['total_raw_records']} | Canonical: {stats['total_canonical_records']} | Duplicates: {stats['total_duplicate_records']}")

    elif args.command == "classify":
        db = FeedbackDatabase(args.db)
        client = GroqClient(model=args.model)
        classifier = BehavioralClassifier(groq_client=client)
        classified = classifier.process_and_save_records(db, limit=args.limit, max_workers=args.workers)
        print(f"\n[OK] Classification run completed. Processed: {len(classified)} records.")

    elif args.command == "evaluate":
        print("\n[*] Running 100-Sample Gold Standard Evaluation Benchmark...")
        client = GroqClient(model=args.model)
        classifier = BehavioralClassifier(groq_client=client)
        evaluator = BenchmarkEvaluator(classifier=classifier)
        report = evaluator.run_benchmark()

        print("\n" + "=" * 65)
        print("=== 100-SAMPLE GOLD STANDARD BENCHMARK ACCURACY REPORT ===")
        print("=" * 65)
        print(f"Total Evaluated Statements:     {report['total_benchmark_samples']}")
        print(f"Overall Accuracy:               {report['accuracy'] * 100:.2f}%")
        print(f"Macro-Averaged F1 Score:        {report['macro_f1'] * 100:.2f}%")
        print(f"Cohen's Kappa Agreement (Kappa):{report['cohens_kappa']:.4f} ({report['inter_rater_agreement_quality']})")
        print(f"Milestone Gate Passed (>85% F1):{'[PASS]' if report['meets_gate_threshold'] else '[FAIL]'}")
        print("\n--- Per-Theme Precision, Recall & F1 Breakdown ---")
        print(f"{'Theme':<22} {'Samples':<9} {'Precision':<11} {'Recall':<9} {'F1-Score':<10}")
        print("-" * 65)
        for theme, m in report["per_theme_report"].items():
            print(f"{theme:<22} {m['samples']:<9} {m['precision']:<11.3f} {m['recall']:<9.3f} {m['f1']:<10.3f}")
        print("=" * 65 + "\n")

    elif args.command == "review":
        db = FeedbackDatabase(args.db)
        mgr = HumanReviewManager(db)
        queue = mgr.get_review_queue(min_confidence_threshold=args.threshold)
        print(f"\n[*] Found {len(queue)} records requiring human review (Confidence < {args.threshold}):\n")
        for item in queue:
            print(f"Record #{item['record_id']} [{item['product_category']} | Source: {item['source']}]")
            print(f"  Theme:      {item['theme']} (Confidence: {item['confidence_score']:.2f})")
            print(f"  Raw Text:   \"{item['raw_text']}\"")
            print(f"  Verbatim:   \"{item['verbatim_evidence']}\"")
            print(f"  Blockers:   {item['purchase_blocker']}")
            print("-" * 65)

    elif args.command == "analytics":
        db = FeedbackDatabase(args.db)
        agg = AnalyticsAggregator(db)
        overview = agg.get_overview_metrics()

        print("\n" + "=" * 55)
        print("=== CONSUMER DISCOVERY BEHAVIORAL ANALYTICS ===")
        print("=" * 55)
        print(f"Total Feedback Records:     {overview['total_raw_records']}")
        print(f"Classified Records:         {overview['total_analyzed_records']}")
        print(f"Average AI Confidence:      {overview['average_confidence_score']:.2f}")
        print(f"External Research Rate:     {overview['external_research_rate_pct']:.1f}%")
        print(f"Comparison Behavior Rate:   {overview['comparison_behavior_rate_pct']:.1f}%\n")

        print("--- Primary Behavioral Themes ---")
        themes = agg.get_theme_distribution(category_filter=args.category)
        for t in themes:
            print(f"  - {t['theme_name']:<35} : {t['count']:>3} ({t['percentage']:>5.1f}%)")

        print("\n--- Top Purchase Blockers ---")
        blockers = agg.get_blocker_matrix(category_filter=args.category)
        for b in blockers[:6]:
            print(f"  - {b['blocker']:<30} : {b['count']:>3} ({b['percentage']:>5.1f}%)")
        print("=" * 55 + "\n")

    elif args.command == "opportunities":
        db = FeedbackDatabase(args.db)
        scorer = OpportunityScorer(db)
        rankings = scorer.compute_opportunity_rankings()

        print("\n" + "=" * 88)
        print("=== OPPORTUNITY PRIORITIZATION MATRIX ===")
        print(f"{'Rank':<5} {'Opportunity Theme':<20} {'Freq %':<8} {'Relevance':<10} {'Impact':<8} {'Solvability':<12} {'Opportunity Score':<18}")
        print("-" * 88)
        for i, opp in enumerate(rankings, 1):
            print(f"#{i:<4} {opp['opportunity_theme']:<20} {opp['frequency_pct']:>5.1f}%     {opp['purchase_relevance_1_5']:>4.1f}       {opp['segment_impact_1_5']:>4.1f}     {opp['solvability_1_5']:>4.1f}         {opp['opportunity_score']:>7.2f} pts")
        print("=" * 88)

        if rankings:
            top = rankings[0]
            print(f"\n[*] Top Ranked Opportunity:")
            print(f"    Theme:       {top['opportunity_theme']} ({top['name']})")
            print(f"    Description: {top['description']}")
            print(f"    Score:       {top['opportunity_score']} / 100")
            if top['evidence_quotes']:
                print(f"    Evidence:    \"{top['evidence_quotes'][0]}\"")
            print("=" * 41 + "\n")

    elif args.command == "ask":
        db = FeedbackDatabase(args.db)
        service = ResearchQueryService(db=db)
        print(f"\n[*] Research Question: \"{args.query}\"")
        if args.category:
            print(f"[*] Filtering by Category: {args.category}")
        if args.theme:
            print(f"[*] Filtering by Theme: {args.theme}")

        response = service.ask(
            query=args.query,
            category_filter=args.category,
            theme_filter=args.theme,
            top_k=args.k,
        )

        print("\n" + "=" * 65)
        print("=== EVIDENCE-GROUNDED SYNTHESIS ===")
        print("=" * 65)
        print(f"\n{response.synthesis_answer}\n")
        print("--- Cited Customer Evidence ---")
        for i, ev in enumerate(response.citations, 1):
            print(f"[{i}] Record #{ev.record_id} ({ev.product_category} | Source: {ev.source})")
            print(f"    Text: \"{ev.text}\"")
            print(f"    Key Quote: \"{ev.verbatim_evidence}\"")
        print("=" * 65 + "\n")

    elif args.command == "search":
        db = FeedbackDatabase(args.db)
        service = ResearchQueryService(db=db)
        hits = service.search_evidence(query=args.query, category_filter=args.category, limit=args.limit)
        print(f"\n[*] Search results for '{args.query}' ({len(hits)} records):\n")
        for h in hits:
            print(f"Record #{h['record_id']} [{h['product_category']} | Source: {h['source']}] (Score: {h['bm25_score']:.2f})")
            print(f"  Theme: {h.get('theme', 'N/A')} | Blocker: {h.get('purchase_blocker', 'N/A')}")
            print(f"  Text:  \"{h['text']}\"")
            print("-" * 65)

    elif args.command == "stats":
        db = FeedbackDatabase(args.db)
        stats = db.get_stats_summary()
        print("\n=== DATABASE SUMMARY ===")
        print(f"Raw Feedback Count:       {stats['total_raw_records']}")
        print(f"Canonical Records:        {stats['total_canonical_records']}")
        print(f"Duplicate Records:        {stats['total_duplicate_records']}")
        print(f"Analyzed Records:         {stats['total_analyzed_records']}")
        print(f"Categories ({len(stats['category_breakdown'])}):        {stats['category_breakdown']}")
        print(f"Sources ({len(stats['source_breakdown'])}):           {stats['source_breakdown']}\n")

    elif args.command == "sample":
        db = FeedbackDatabase(args.db)
        conn = db.get_connection()
        try:
            df = conn.execute(f"""
                SELECT r.record_id, r.product_category, b.theme, b.verbatim_evidence, b.confidence_score
                FROM raw_feedback r
                JOIN behavioral_records b ON r.record_id = b.record_id
                LIMIT {args.limit}
            """).fetchdf()
            print("\n=== SAMPLE CLASSIFIED RECORDS ===")
            for _, row in df.iterrows():
                print(f"Record #{row['record_id']} [{row['product_category']}] -> Theme: {row['theme']} (Conf: {row['confidence_score']:.2f})")
                print(f"  Evidence: \"{row['verbatim_evidence']}\"")
            print()
        finally:
            conn.close()


if __name__ == "__main__":
    main()
