"""检查新阳光幼儿园数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

code = "10107"

print(f"=== 新阳光幼儿园 ({code}) ===")
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code=:c", {"c": code}).iloc[0,0]
print(f"总行数: {cnt}")

print("\n=== 所有科目 ===")
df = execute_sql("""
  SELECT account_code, account_name, direction, SUM(ending_balance) as balance
  FROM account_balance WHERE company_code=:c
  GROUP BY account_code, account_name, direction
  ORDER BY account_code
""", {"c": code})
print(df.to_string(index=False))

print("\n=== 检查实收资本相关 ===")
df2 = execute_sql("""
  SELECT account_code, account_name, ending_balance, direction, assist_dimensions
  FROM account_balance WHERE company_code=:c AND account_name LIKE '%实收%'
""", {"c": code})
print(df2.to_string(index=False))
if len(df2) == 0:
    print("(无数据)")

print("\n=== 导入记录 ===")
df3 = execute_sql("SELECT file_name, company_code, batch_no FROM import_logs WHERE company_code=:c", {"c": code})
print(df3.to_string(index=False))
