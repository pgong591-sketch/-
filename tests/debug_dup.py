"""检查公司重复和拔创中心问题"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 查找名称带"拔创"的公司
print("=== 拔创相关公司 ===")
df = execute_sql("SELECT code, name, parent_code, level FROM companies WHERE name LIKE '%拔创%'")
for _, r in df.iterrows():
    print(f"  {r['code']:15s} | {r['name']:20s} | parent: {r['parent_code']} | level: {r['level']}")

# 查找名称完全相同的公司
print("\n=== 名称重复的公司 ===")
df2 = execute_sql("SELECT name, COUNT(*) as cnt FROM companies GROUP BY name HAVING cnt > 1")
for _, r in df2.iterrows():
    print(f"  {r['name']} ({r['cnt']}次)")
    details = execute_sql("SELECT code, name, parent_code FROM companies WHERE name = :n", {"n": r["name"]})
    for _, d in details.iterrows():
        print(f"    {d['code']} - parent: {d['parent_code']}")

print("\n=== companies 总记录数 ===")
cnt = execute_sql("SELECT COUNT(*) as cnt FROM companies").iloc[0, 0]
print(f"  共 {cnt} 条")

# 查找可能的残留旧数据（编码不是纯数字也不是ROOT）
print("\n=== 非标准编码的公司 ===")
df3 = execute_sql("SELECT code, name FROM companies WHERE code NOT GLOB '[0-9]*' AND code != 'ROOT'")
for _, r in df3.iterrows():
    print(f"  {r['code']:15s} | {r['name']}")
