"""检查现有数据库和代码结构"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

print("=== 所有表 ===")
df = execute_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print(df.to_string(index=False))

print("\n=== balance_sheet_template 结构 ===")
try:
    df2 = execute_sql("PRAGMA table_info(balance_sheet_template)")
    print(df2.to_string(index=False))
except:
    print("(不存在)")

print("\n=== 现有导入解析器类 ===")
# 检查import_parser.py中的解析器
import ast, inspect
from src import import_parser
classes = []
for name, obj in inspect.getmembers(import_parser):
    if inspect.isclass(obj) and hasattr(obj, 'TABLE_NAME'):
        classes.append((name, obj.TABLE_NAME))
for n, t in classes:
    print(f"  {n} -> {t}")
