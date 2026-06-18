"""清理测试残留的孤立公司数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session, execute_sql
from sqlalchemy import text

session = get_session()
session.execute(text("DELETE FROM companies WHERE parent_code IS NULL AND code != 'ROOT'"))
session.commit()
session.close()

print("已清理孤立公司")

# 验证
tree = execute_sql("SELECT code, name, level, tree_path FROM companies ORDER BY tree_path")
print(f"当前共 {len(tree)} 家公司")
for _, r in tree.iterrows():
    indent = "  " * r["level"]
    print(f'{indent}{r["code"]:8s} {r["name"]}')
