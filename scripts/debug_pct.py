"""调试百分比数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT DISTINCT item_name FROM income_statement WHERE item_name LIKE '%毛利%' OR item_name LIKE '%净利率%'")
print("含百分比的科目:")
print(df.to_string(index=False))

df2 = execute_sql("SELECT item_name, period1_value FROM income_statement WHERE (item_name LIKE '%毛利%' OR item_name LIKE '%净利率%') AND period='202603' LIMIT 5")
print("\n数据样例:")
print(df2.to_string(index=False))
