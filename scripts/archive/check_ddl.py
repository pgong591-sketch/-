"""检查真实库各表的DDL"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

tables = ["companies", "company_aliases", "ownership", "account_balance", "balance_sheet", "income_statement", "import_logs", "financial_report_data"]
for t in tables:
    df = execute_sql(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'")
    if len(df) > 0:
        sql = df.iloc[0]["sql"]
        print(f"\n-- {t}")
        print(sql)
