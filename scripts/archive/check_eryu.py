"""检查尔遇书馆相关公司和导入映射"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

print("=== 含'尔遇'的公司 ===")
df = execute_sql("SELECT code, name, short_name FROM companies WHERE name LIKE '%尔遇%' OR short_name LIKE '%尔遇%'")
print(df.to_string(index=False))

print("\n=== 含'东城'的公司 ===")
df2 = execute_sql("SELECT code, name, short_name FROM companies WHERE name LIKE '%东城%'")
print(df2.to_string(index=False))

print("\n=== 导入文件中含'尔遇'的 ===")
df3 = execute_sql("SELECT file_name, company_code FROM import_logs WHERE file_name LIKE '%尔遇%'")
print(df3.to_string(index=False))
