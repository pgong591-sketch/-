"""检查莞城小学部数据详细"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT item_name, period1_value, cumulative_value, sort_order FROM income_statement WHERE original_name='莞城小学部' AND period='202603' ORDER BY sort_order")
print(f'总行数: {len(df)}')
print(df.to_string(index=False))
