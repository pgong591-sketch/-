"""检查管理中心导入结果"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 看导入日志
logs = execute_sql("SELECT company_code, period, report_type, status, file_name FROM import_logs ORDER BY created_at DESC LIMIT 5")
print("最近导入:")
for _, r in logs.iterrows():
    print(f"  company={r['company_code']} period={r['period']} type={r['report_type']} status={r['status']} file={r['file_name']}")

# 看101的数据
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
print(f"\n101 (广东多维) 数据量: {cnt} 行")

# 所有公司编码
codes = execute_sql("SELECT DISTINCT company_code FROM account_balance ORDER BY company_code")
print(f"\naccount_balance 中有数据的公司 ({len(codes)} 个):")
for _, r in codes.iterrows():
    print(f"  {r['company_code']}")

# 看是否有"管理中心"作为编码的残留
cnt_mgr = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '管理中心'").iloc[0, 0]
print(f"\n'管理中心'旧数据: {cnt_mgr} 行")
