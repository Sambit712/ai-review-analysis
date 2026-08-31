import pandas as pd

excel_path = r'Docs/nykaa_ai_discovery_database_plus_25_test_statements.xlsx'

print('=== TAXONOMY ===')
df_tax = pd.read_excel(excel_path, sheet_name='Taxonomy')
for idx, row in df_tax.iterrows():
    print(f"{row['Dimension']}:")
    print(f"  Allowed: {row['Allowed values']}")
    print(f"  Def: {row['Definition']}\n")

print('=== FEEDBACK RAW ALL 35 STATEMENTS ===')
df_raw = pd.read_excel(excel_path, sheet_name='Feedback_Raw')
print(f"Total raw records: {len(df_raw)}")
for idx, row in df_raw.iterrows():
    print(f"[{row['record_id']}] ({row['source']} | {row['product_category']}): {str(row['text'])[:120]}")

print('\n=== AI CLASSIFICATION GROUND TRUTH (10 statements) ===')
df_ai = pd.read_excel(excel_path, sheet_name='AI_Classification')
print(f"Total AI classification rows: {len(df_ai)}")
for idx, row in df_ai.head(5).iterrows():
    print(f"[{row['record_id']}] Intent: {row['wishlist_intent']} | Blocker: {row['purchase_blocker']} | Gap: {row['information_gap']} | Trigger: {row['decision_trigger']}")

print('\n=== OPPORTUNITY SCORING SHEET ===')
df_opp = pd.read_excel(excel_path, sheet_name='Opportunity_Scoring')
print(df_opp)
