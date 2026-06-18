"""检查南城华凯数据映射"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 查account_balance中不在companies表里的编码
df = execute_sql("""
  SELECT DISTINCT ab.company_code 
  FROM account_balance ab 
  LEFT JOIN companies c ON ab.company_code = c.code 
  WHERE c.code IS NULL
""")
print("=== 无对应公司的编码 ===")
print(df.to_string(index=False))

# 查华凯校区数据
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code='101010102'").iloc[0,0]
print(f"\n=== 华凯校区 101010102 数据: {cnt} 行 ===")

# 查所有公司
companies = execute_sql("SELECT code, name, short_name FROM companies ORDER BY code")
print("\n=== 所有公司 ===")
print(companies.to_string(index=False))

# 查导入文件的文件名
files = execute_sql("SELECT file_name, company_code FROM import_logs ORDER BY file_name")
print("\n=== 导入文件列表 ===")
print(files.to_string(index=False))
