"""检查资产负债表导入和查询问题"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

print("=== 资产负债表导入记录 ===")
df = execute_sql("SELECT file_name, company_code, period, status, batch_no FROM import_logs WHERE report_type='balance_sheet' ORDER BY created_at DESC")
print(df.to_string(index=False))

print("\n=== balance_sheet 表中的公司 ===")
df2 = execute_sql("SELECT DISTINCT company_code, period FROM balance_sheet ORDER BY company_code, period")
print(df2.to_string(index=False))

print("\n=== 万江校区(101010104) 公司信息 ===")
df3 = execute_sql("SELECT code, name, short_name FROM companies WHERE code='101010104'")
print(df3.to_string(index=False))

print("\n=== 东莞非学科管理中心(1010101) 公司信息 ===")
df4 = execute_sql("SELECT code, name, short_name FROM companies WHERE code='1010101'")
print(df4.to_string(index=False))

print("\n=== 广东多维(101) 公司信息 ===")
df5 = execute_sql("SELECT code, name, short_name FROM companies WHERE code='101'")
print(df5.to_string(index=False))
