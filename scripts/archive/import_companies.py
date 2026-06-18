"""导入公司层级 Excel 到数据库"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import re
from src.db_connection import init_database, get_session
from sqlalchemy import text
from src.company_hierarchy import rebuild_tree_path

# 读取 Excel
df = pd.read_excel("data/集团公司开业时间统计.xlsx", header=5)
df = df.dropna(subset=["公司编码"])  # 去掉空行

# 过滤掉页脚行
df = df[~df["公司编码"].astype(str).str.contains("制表|第.*页", na=False)]

# 清理公司名称和上级公司名称（去掉换行和多余空格）
df["公司名称"] = df["公司名称"].astype(str).str.replace(r"\s+", "", regex=True)
df["上级公司"] = df["上级公司"].astype(str).str.replace(r"\s+", "", regex=True)

# 构建名称→编码映射
name_to_code = {}
for _, r in df.iterrows():
    name = r["公司名称"].strip()
    code = str(r["公司编码"]).strip()
    if name and code:
        name_to_code[name] = code

print(f"读取到 {len(df)} 条公司记录")
print(f"名称→编码映射: {len(name_to_code)} 个")

# 数据库操作
session = get_session()

# 添加顶级根节点"多维教育集团"（如果不存在）
root = session.execute(text("SELECT code FROM companies WHERE code = 'ROOT'")).fetchone()
if not root:
    session.execute(
        text("INSERT OR IGNORE INTO companies (code, name, parent_code, level, is_consolidated, status) VALUES (:c, :n, :p, 0, 1, 1)"),
        {"c": "ROOT", "n": "多维教育集团", "p": None}
    )

# 导入所有公司
total = 0
for _, r in df.iterrows():
    code = str(r["公司编码"]).strip()
    name = str(r["公司名称"]).strip()
    parent_name = str(r["上级公司"]).strip()

    # 通过父级名称找父级编码
    parent_code = None
    if parent_name and parent_name in name_to_code:
        parent_code = name_to_code[parent_name]
    elif parent_name == "多维教育集团":
        parent_code = "ROOT"

    # 插入公司
    session.execute(
        text("""INSERT OR IGNORE INTO companies
                (code, name, short_name, parent_code, level, is_consolidated, status)
                VALUES (:c, :n, :n, :p, 1, 1, 1)"""),
        {"c": code, "n": name, "p": parent_code}
    )
    total += 1

session.commit()

# 重建树路径
rebuild_tree_path("ROOT")

session.close()
print(f"✅ 成功导入 {total} 家公司，树路径已重建")

# 验证
from src.db_connection import execute_sql
tree = execute_sql("SELECT code, name, parent_code, level, tree_path FROM companies ORDER BY tree_path")
for _, r in tree.iterrows():
    indent = "  " * r["level"]
    print(f'{indent}{r["code"]:8s} {r["name"]} (path: {r["tree_path"]})')
