"""根据更新后的公司Excel更新数据库中的公司层级和简称映射"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.db_connection import get_session, execute_sql
from sqlalchemy import text
from src.company_hierarchy import rebuild_tree_path, get_company_tree

# 读取Excel
df = pd.read_excel("data/集团公司开业时间统计.xlsx", header=5)
# 过滤页脚
df = df[df["公司编码"].astype(str).str.match(r"^\d+$")]

print(f"读取到 {len(df)} 条公司记录")
print(f"列: {list(df.columns)}")

# 构建简称映射
short_to_code = {}
code_to_short = {}
for _, r in df.iterrows():
    code = str(r["公司编码"]).strip()
    name = str(r["公司名称"]).strip()
    short = str(r["简称"]).strip() if pd.notna(r.get("简称")) else ""
    if code and name:
        short_to_code[name] = code
        if short:
            short_to_code[short] = code
            code_to_short[code] = short

# 额外映射
for s, c in {
    "管理中心": "101",
    "非学科管理中心": "1010101",
    "莞城小学": "101010120",
    "莞城高中": "101010121",
    "莞城初中": "101010128",
    "莞城个性化": "101010129",
}.items():
    short_to_code[s] = c

print(f"\n简称→编码映射: {len(short_to_code)} 个")

# 更新companies表
session = get_session()
updated = 0
inserted = 0

for _, r in df.iterrows():
    code = str(r["公司编码"]).strip()
    name = str(r["公司名称"]).strip()
    parent_name = str(r["上级公司"]).strip() if pd.notna(r.get("上级公司")) else ""
    short = str(r["简称"]).strip() if pd.notna(r.get("简称")) else ""

    # 找父编码
    parent_code = None
    if parent_name:
        parent_code = short_to_code.get(parent_name)
        if not parent_code:
            pc = session.execute(text("SELECT code FROM companies WHERE name = :n"), {"n": parent_name}).fetchone()
            if pc:
                parent_code = pc[0]
            elif parent_name == "多维教育集团":
                parent_code = "ROOT"

    # 检查是否存在
    exist = session.execute(text("SELECT code FROM companies WHERE code = :c"), {"c": code}).fetchone()
    if exist:
        session.execute(
            text("UPDATE companies SET name = :n, parent_code = :p WHERE code = :c"),
            {"n": name, "p": parent_code, "c": code}
        )
        updated += 1
    else:
        session.execute(
            text("INSERT INTO companies (code, name, short_name, parent_code, level, is_consolidated, status) VALUES (:c, :n, :s, :p, 1, 1, 1)"),
            {"c": code, "n": name, "s": short or name, "p": parent_code}
        )
        inserted += 1

session.commit()
print(f"更新 {updated} 条, 新增 {inserted} 条")

# 重建树路径
roots = session.execute(text("SELECT code FROM companies WHERE parent_code IS NULL OR parent_code = ''")).fetchall()
for r in roots:
    rebuild_tree_path(r[0])

session.close()
print("树路径已重建")

# 更新 account_balance 中的旧简称编码
print("\n--- 修复 account_balance 中的简称编码 ---")
ab_codes = execute_sql("SELECT DISTINCT company_code FROM account_balance")
fixed = 0
for _, row in ab_codes.iterrows():
    old = row["company_code"]
    new = short_to_code.get(str(old))
    if new and str(new) != str(old):
        session2 = get_session()
        try:
            session2.execute(text("DELETE FROM account_balance WHERE company_code = :n AND period IN (SELECT DISTINCT period FROM account_balance WHERE company_code = :o)"), {"n": new, "o": old})
            session2.execute(text("UPDATE account_balance SET company_code = :n WHERE company_code = :o"), {"n": new, "o": old})
            session2.commit()
            print(f"  {old:20s} -> {new}")
            fixed += 1
        except Exception as e:
            session2.rollback()
            print(f"  {old:20s} -> {new} 失败: {e}")
        finally:
            session2.close()

print(f"修复 {fixed} 条")

# 验证
print(f"\n--- 当前层级树 ---")
tree = get_company_tree()
for _, r in tree.iterrows():
    indent = "  " * r["level"]
    print(f'{indent}{r["code"]:10s} {r["name"]}')

print(f"\n✅ 完成! 共 {len(tree)} 家公司")
