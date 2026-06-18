"""检查公司列顺序"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT original_name FROM income_statement WHERE period='202603' ORDER BY sort_order")
order = df['original_name'].dropna().unique().tolist()
print(f'公司数量: {len(order)}')
for i, n in enumerate(order):
    print(f'  {i+1}. {n}')
