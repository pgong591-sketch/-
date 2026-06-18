"""检查拔创中心导入数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 最近导入记录
logs = execute_sql("SELECT batch_no, company_code, period, report_type, status, file_name FROM import_logs ORDER BY created_at DESC LIMIT 5")
print("最近导入记录:")
for _, r in logs.iterrows():
    print(f"  {r['file_name']} | company={r['company_code']} | period={r['period']} | status={r['status']}")

# account_balance 中拔创的数据
ab = execute_sql("SELECT DISTINCT company_code, period FROM account_balance WHERE company_code LIKE '%拔创%' OR company_code = '101010136'")
print(f"\n拔创中心在 account_balance:")
for _, r in ab.iterrows():
    print(f"  company={r['company_code']}, period={r['period']}")

cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101010136'")
print(f"  101010136 数据量: {cnt.iloc[0,0]} 行")

# 如果数据存在但公司编码不是101010136
other = execute_sql("SELECT company_code, COUNT(*) as cnt FROM account_balance WHERE company_code LIKE '%拔创%' GROUP BY company_code")
if len(other) > 0:
    print(f"\n其他编码的拔创数据:")
    for _, r in other.iterrows():
        print(f"  {r['company_code']}: {r['cnt']} 行")
