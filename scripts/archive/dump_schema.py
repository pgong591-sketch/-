"""导出现有数据库完整 schema 并与 init.sql 对比"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql, get_engine
from sqlalchemy import inspect

engine = get_engine()
inspector = inspect(engine)

print("=" * 80)
print("真实数据库完整 schema")
print("=" * 80)

for table_name in inspector.get_table_names():
    if table_name == "sqlite_sequence":
        continue
    print(f"\n-- {table_name}")
    cols = inspector.get_columns(table_name)
    pk = inspector.get_pk_constraint(table_name)
    pk_cols = pk.get("constrained_columns", [])
    
    col_defs = []
    for col in cols:
        name = col["name"]
        ctype = str(col["type"])
        nullable = " NOT NULL" if not col["nullable"] else ""
        default = f" DEFAULT {col['default']}" if col["default"] is not None else ""
        is_pk = " PRIMARY KEY" if name in pk_cols else ""
        col_defs.append(f"    {name} {ctype}{nullable}{default}{is_pk}")
    
    print(f"CREATE TABLE IF NOT EXISTS {table_name} (")
    print(",\n".join(col_defs))
    print(");")
