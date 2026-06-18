"""最终重建树路径"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.company_hierarchy import rebuild_tree_path
from src.db_connection import execute_sql

rebuild_tree_path("ROOT")
print("树路径已重建")

bad = execute_sql("SELECT COUNT(*) as cnt FROM companies WHERE tree_path IS NULL OR tree_path = ''").iloc[0, 0]
print(f"仍有问题的: {bad} 家")

tree = execute_sql("SELECT code, name, level, tree_path FROM companies ORDER BY tree_path")
print(f"完整层级树 ({len(tree)} 家):")
for _, r in tree.iterrows():
    indent = "  " * r["level"]
    print(f'{indent}{r["code"]} {r["name"]}')
