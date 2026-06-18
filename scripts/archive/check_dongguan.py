"""检查东莞国际校区数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

code = "101020101"

print(f"=== {code} 东莞国际校区 ===")
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code=:c", {"c": code}).iloc[0,0]
print(f"总行数: {cnt}")

print("\n=== 科目列表 ===")
df = execute_sql("""
  SELECT account_code, account_name, direction, SUM(ending_balance) as balance
  FROM account_balance WHERE company_code=:c
  GROUP BY account_code, account_name, direction
  ORDER BY account_code
""", {"c": code})
print(df.to_string(index=False))

print("\n=== 期末余额合计 ===")
total = execute_sql("SELECT SUM(ending_balance) as total FROM account_balance WHERE company_code=:c", {"c": code}).iloc[0,0]
print(f"合计: {total}")

print("\n=== 检查是否有脏数据 ===")
dirty = execute_sql("""
  SELECT account_code, account_name FROM account_balance
  WHERE company_code=:c AND (
    account_code LIKE '%科目%' OR account_name LIKE '%科目%'
    OR account_code LIKE '%制单%' OR account_name LIKE '%制单%'
    OR account_code LIKE '%打印%' OR account_name LIKE '%打印%'
  )
""", {"c": code})
print(f"脏数据: {len(dirty)} 行")
if len(dirty) > 0:
    print(dirty.to_string(index=False))
