"""检查营业收入各公司数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT original_name, sort_order, period1_value FROM income_statement WHERE item_name='一、营业收入' AND period='202603' ORDER BY sort_order")
print(f'公司数: {len(df)}')
print(df.to_string(index=False))
