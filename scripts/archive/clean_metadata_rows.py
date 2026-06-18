"""清理制单人/打印日期等脏数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql, get_session
from sqlalchemy import text

# 查所有脏数据
print("=== 清理前检查 ===")
bad = execute_sql("""
  SELECT company_code, COUNT(*) as cnt 
  FROM account_balance 
  WHERE account_name LIKE '%制单%' 
     OR account_name LIKE '%打印%'
     OR account_name LIKE '%科目编码%'
  GROUP BY company_code
""")
print(bad.to_string(index=False))
total_all = bad["cnt"].sum() if len(bad) > 0 else 0
print(f"共 {total_all} 行脏数据\n")

# 删除
session = get_session()
rowcount = session.execute(text("""
  DELETE FROM account_balance 
  WHERE account_name LIKE '%制单%' 
     OR account_name LIKE '%打印%'
     OR account_name LIKE '%科目编码%'
"""))
session.commit()
print(f"✅ 共删除 {rowcount.rowcount} 行脏数据")

# 复查
print("\n=== 清理后复查 ===")
bad2 = execute_sql("""
  SELECT COUNT(*) as cnt FROM account_balance 
  WHERE account_name LIKE '%制单%' 
     OR account_name LIKE '%打印%'
     OR account_name LIKE '%科目编码%'
""")
print(f"剩余脏数据: {bad2.iloc[0,0]} 条")
session.close()
