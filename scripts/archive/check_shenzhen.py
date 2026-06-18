"""查深圳卓越还有无脏数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

print("=== 含'科目'/'编码'的异常行 ===")
df = execute_sql("""
  SELECT account_code, account_name, ending_balance, direction
  FROM account_balance 
  WHERE company_code='1010201' 
    AND (account_code LIKE '%科目%' OR account_name LIKE '%科目%' 
         OR account_code LIKE '%编码%')
""")
print(df.to_string(index=False))

print("\n=== 按account_code排序看最后几行 ===")
df2 = execute_sql("""
  SELECT account_code, account_name, ending_balance
  FROM account_balance 
  WHERE company_code='1010201' 
  ORDER BY account_code
""")
print(df2.tail(10).to_string(index=False))

print("\n=== 总行数 ===")
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code='1010201'").iloc[0,0]
print(f"{cnt} 行")
