"""检查损益表导入错误"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

df = execute_sql("SELECT file_name, company_code, period, status, report_type FROM import_logs ORDER BY created_at DESC LIMIT 5")
print("=== 最新导入记录 ===")
print(df.to_string(index=False))

# 查是否有错误日志
try:
    ef = execute_sql("SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 10")
    print("\n=== 错误日志 ===")
    print(ef.to_string(index=False))
except:
    print("\n(无错误日志表)")

# 查当前数据
cnt = execute_sql("SELECT COUNT(*) as c FROM income_statement").iloc[0,0]
print(f"\n损益表数据: {cnt} 行")
if cnt > 0:
    df2 = execute_sql("SELECT company_code, original_name, COUNT(*) as c FROM income_statement GROUP BY company_code ORDER BY c DESC")
    print(df2.to_string(index=False))
