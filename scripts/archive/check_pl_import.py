"""检查拔创中心损益表导入情况"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT file_name, company_code, period, status, report_type FROM import_logs ORDER BY created_at DESC")
print("=== 最新导入记录 ===")
print(df.head(10).to_string(index=False))

df2 = execute_sql("SELECT company_code, original_name, COUNT(*) as c FROM income_statement GROUP BY company_code")
print(f"\n=== 损益表数据: {len(df2)} 条 ===")
if len(df2) > 0:
    print(df2.to_string(index=False))
else:
    print("(空)")

df3 = execute_sql("SELECT period, COUNT(*) as c FROM income_statement GROUP BY period")
print(f"\n=== 期间分布 ===")
print(df3.to_string(index=False))
