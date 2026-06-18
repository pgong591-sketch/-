"""清理残留的重复公司数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session, execute_sql
from sqlalchemy import text

session = get_session()
# 删除编码不是纯数字且不是ROOT的旧残留
rows = session.execute(text("SELECT code FROM companies WHERE code NOT GLOB '[0-9]*' AND code != 'ROOT'")).fetchall()
print(f"找到 {len(rows)} 条非标准编码的残留:")
for r in rows:
    print(f"  删除: {r[0]}")
    session.execute(text("DELETE FROM companies WHERE code = :c"), {"c": r[0]})

# 清理孤立无父节点的（非ROOT）
orphans = session.execute(text("SELECT code FROM companies WHERE parent_code IS NULL AND code != 'ROOT'")).fetchall()
print(f"找到 {len(orphans)} 条孤立公司:")
for r in orphans:
    print(f"  删除: {r[0]}")
    session.execute(text("DELETE FROM companies WHERE code = :c"), {"c": r[0]})

session.commit()
session.close()

# 验证
tree = execute_sql("SELECT code, name FROM companies ORDER BY code")
print(f"\n清理后共 {len(tree)} 家公司")
dup = execute_sql("SELECT name, COUNT(*) as cnt FROM companies GROUP BY name HAVING cnt > 1")
if len(dup) > 0:
    print(f"仍有重复名称:")
    print(dup.to_string())
else:
    print("✅ 无重复名称")
