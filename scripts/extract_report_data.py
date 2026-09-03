import duckdb
import json
import pandas as pd

def extract_all():
    con = duckdb.connect('data/raw_db/feedback.duckdb', read_only=True)
    
    total_raw = con.execute("SELECT COUNT(*) FROM raw_feedback").fetchone()[0]
    total_canonical = con.execute("SELECT COUNT(*) FROM raw_feedback WHERE is_duplicate = FALSE").fetchone()[0]
    total_analyzed = con.execute("SELECT COUNT(*) FROM behavioral_records").fetchone()[0]
    flagged = con.execute("SELECT COUNT(*) FROM behavioral_records WHERE status IN ('NEEDS_REVIEW', 'REQUIRES_REVIEW')").fetchone()[0]
    avg_conf = con.execute("SELECT AVG(confidence_score) FROM behavioral_records").fetchone()[0]
    
    print(f"Total Raw: {total_raw}, Canonical: {total_canonical}, Analyzed: {total_analyzed}, Flagged: {flagged}, Avg Conf: {avg_conf:.4f}")
    
    # Themes
    print("\n--- THEMES ---")
    themes = con.execute(f"""
        SELECT theme, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM behavioral_records 
        GROUP BY theme 
        ORDER BY cnt DESC
    """).fetchall()
    for t in themes:
        print(t)
        
    # Blockers
    print("\n--- PURCHASE BLOCKERS ---")
    blockers = con.execute(f"""
        SELECT b, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM (SELECT unnest(purchase_blocker) as b FROM behavioral_records) 
        GROUP BY b 
        ORDER BY cnt DESC
    """).fetchall()
    for b in blockers:
        print(b)
        
    # Info Gaps
    print("\n--- INFO GAPS ---")
    gaps = con.execute(f"""
        SELECT g, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM (SELECT unnest(information_gap) as g FROM behavioral_records) 
        GROUP BY g 
        ORDER BY cnt DESC
    """).fetchall()
    for g in gaps:
        print(g)
        
    # Intents
    print("\n--- WISHLIST INTENTS ---")
    intents = con.execute(f"""
        SELECT wishlist_intent, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM behavioral_records 
        GROUP BY wishlist_intent 
        ORDER BY cnt DESC
    """).fetchall()
    for i in intents:
        print(i)
        
    # External Research
    print("\n--- EXTERNAL RESEARCH ---")
    ext = con.execute(f"""
        SELECT r, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM (SELECT unnest(external_research) as r FROM behavioral_records) 
        WHERE r != 'NONE' 
        GROUP BY r 
        ORDER BY cnt DESC
    """).fetchall()
    for e in ext:
        print(e)
        
    # Decision Triggers
    print("\n--- DECISION TRIGGERS ---")
    triggers = con.execute(f"""
        SELECT d, count(*) as cnt, round(count(*)*100.0/{total_analyzed}, 2) as pct 
        FROM (SELECT unnest(decision_trigger) as d FROM behavioral_records) 
        GROUP BY d 
        ORDER BY cnt DESC
    """).fetchall()
    for tr in triggers:
        print(tr)
        
    # Category Distribution
    print("\n--- CATEGORIES ---")
    cats = con.execute(f"""
        SELECT product_category, count(*) as cnt, round(count(*)*100.0/{total_raw}, 2) as pct 
        FROM raw_feedback 
        GROUP BY product_category 
        ORDER BY cnt DESC
    """).fetchall()
    for c in cats:
        print(c)
        
    # Opportunity Scores
    print("\n--- OPPORTUNITIES ---")
    opps = con.execute("""
        SELECT opportunity_theme, frequency_count, frequency_pct, purchase_relevance_1_5, segment_impact_1_5, solvability_1_5, opportunity_score 
        FROM opportunity_scores 
        ORDER BY opportunity_score DESC
    """).fetchall()
    for o in opps:
        print(o)
        
    con.close()

if __name__ == '__main__':
    extract_all()
