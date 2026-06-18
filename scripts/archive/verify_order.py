"""验证公司排列顺序"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("""
  SELECT COALESCE(c.name, ab.company_code) AS company_name
  FROM income_statement ab
  LEFT JOIN companies c ON ab.company_code = c.code
  WHERE ab.period='202603'
  ORDER BY ab.sort_order
""")
order = df["company_name"].drop_duplicates().tolist()
print(f"公司数量: {len(order)}")
for i, n in enumerate(order):
    print(f"  {i+1}. {n}")
