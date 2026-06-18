"""调试查询: 检查科目余额表和公司表数据匹配情况"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

print("=== account_balance 中的公司编码 ===")
ab = execute_sql("SELECT DISTINCT company_code FROM account_balance ORDER BY company_code")
if len(ab) > 0:
    for _, r in ab.iterrows():
        print(f"  '{r['company_code']}'")
else:
    print("  (空)")

print(f"\n=== companies 表中的公司 ({len(execute_sql('SELECT * FROM companies'))} 家) ===")
co = execute_sql("SELECT code, name FROM companies ORDER BY code")
if len(co) > 0:
    for _, r in co.iterrows():
        print(f"  {r['code']:8s} - {r['name']}")
else:
    print("  (空)")

print("\n=== 取交集: 有数据的公司 ===")
ab_codes = set(ab["company_code"].tolist())
co_codes = set(co["code"].tolist())
match = ab_codes & co_codes
missing_in_co = ab_codes - co_codes
if match:
    print(f"  数据中且有公司记录的: {match}")
if missing_in_co:
    print(f"  数据中有但公司表无此编码: {missing_in_co}")

print("\n=== 检查最近一条导入数据 ===")
logs = execute_sql("SELECT company_code, period, report_type FROM import_logs ORDER BY created_at DESC LIMIT 3")
if len(logs) > 0:
    print(logs.to_string())
else:
    print("  (无导入记录)")
