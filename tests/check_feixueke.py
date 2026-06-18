"""检查非学科管理中心数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 导入记录
logs = execute_sql("SELECT company_code, period, file_name, status FROM import_logs WHERE file_name LIKE '%非学科%' ORDER BY created_at DESC")
print("非学科导入记录:")
for _, r in logs.iterrows():
    print(f"  {r['file_name']} -> company={r['company_code']} status={r['status']}")

# 如果没有，看最近几条
if len(logs) == 0:
    print("  (无记录)")
    logs2 = execute_sql("SELECT company_code, period, file_name, status FROM import_logs ORDER BY created_at DESC LIMIT 5")
    print("\n最近5条:")
    for _, r in logs2.iterrows():
        print(f"  {r['file_name']} -> company={r['company_code']}")

# 数据量
cnt1 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '1010101'").iloc[0, 0]
cnt2 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
print(f"\n1010101 (东莞非学科管理中心): {cnt1} 行")
print(f"101 (广东多维教育科技集团): {cnt2} 行")
