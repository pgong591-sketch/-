"""修复万江映射并查其他公司"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

# 查万江导入详情
print("=== 万江导入记录详情 ===")
df = execute_sql("""
    SELECT batch_no, file_name, company_code, period
    FROM import_logs WHERE file_name LIKE '%万江%' AND report_type='balance_sheet'
""")
print(df.to_string(index=False))
batch_no = df.iloc[0]["batch_no"] if len(df) > 0 else None

print("\n=== 搜索 data 目录下的资产负债表文件 ===")
import os
files = [f for f in os.listdir("data") if f.endswith(".xls") and "资产负债" in f]
for f in sorted(files):
    print(f"  {f}")
