"""验证资产负债表数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

cnt = execute_sql("SELECT COUNT(*) as c FROM balance_sheet WHERE company_code='101010136' AND period='202603'").iloc[0,0]
print(f"行数: {cnt}")

if cnt > 0:
    df = execute_sql("SELECT side, item_name, sort_order FROM balance_sheet WHERE company_code='101010136' AND period='202603' ORDER BY sort_order")
    print(df.to_string(index=False))
