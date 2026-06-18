"""检查公司层级树完整性"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql
from src.company_hierarchy import rebuild_tree_path, get_company_tree

# 检查异常
bad = execute_sql("SELECT code, name, parent_code FROM companies WHERE parent_code IS NULL AND code != 'ROOT'")
if len(bad) > 0:
    print(f"无父节点: {len(bad)} 家")
    for _, r in bad.iterrows():
        print(f"  {r['code']} {r['name']}")

no_tree = execute_sql("SELECT code, name, parent_code, level FROM companies WHERE tree_path IS NULL OR tree_path = ''")
if len(no_tree) > 0:
    print(f"\n无树路径: {len(no_tree)} 家")
    for _, r in no_tree.iterrows():
        print(f"  {r['code']} {r['name']} (parent: {r['parent_code']})")

# 如果有无树路径的，重建
if len(no_tree) > 0 or len(bad) > 0:
    print("\n修复: 重新指定父节点并重建树...")
    from src.db_connection import get_session
    from sqlalchemy import text
    session = get_session()
    fixes = {
        "101010137": "10101",  # 多维个性化智学中心 -> 多维培优
        "1010502": "101",      # 东莞加佳物业 -> 广东多维
        "10111": "101",        # 无限问教育 -> 广东多维
        "10112": "101",        # 东莞赫布科技 -> 广东多维
        "10115": "101",        # 集多好教育 -> 广东多维
        "103": "10115",        # 茵维特幼儿公学 -> 集多好教育
        "104": "10115",        # 深圳茵维特 -> 集多好教育
        "10205": "102",        # 深圳和顺冠成 -> 深圳尔遇
    }
    for code, parent in fixes.items():
        session.execute(text("UPDATE companies SET parent_code = :p WHERE code = :c"), {"p": parent, "c": code})
    session.commit()
    
    roots = session.execute(text("SELECT code FROM companies WHERE parent_code IS NULL OR parent_code = ''")).fetchall()
    for r in roots:
        rebuild_tree_path(r[0])
    session.close()

# 最终验证
tree = get_company_tree()
print(f"\n最终层级树 ({len(tree)} 家):")
for _, r in tree.iterrows():
    indent = "  " * r["level"]
    print(f'{indent}{r["code"]:10s} {r["name"]}')

still_bad = execute_sql("SELECT COUNT(*) FROM companies WHERE tree_path IS NULL OR tree_path = ''").iloc[0, 0]
print(f"\n仍有问题的: {still_bad} 家")
