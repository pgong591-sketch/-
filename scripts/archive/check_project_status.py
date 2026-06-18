"""全面检查数据库和项目状态"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

print("=" * 60)
print("1. 数据库表清单")
print("=" * 60)
tables = execute_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for t in tables["name"]:
    cnt = execute_sql(f"SELECT COUNT(*) as c FROM \"{t}\"").iloc[0, 0]
    print(f"  {t}: {cnt} 行")

print("\n" + "=" * 60)
print("2. 公司层级")
print("=" * 60)
comp = execute_sql("SELECT COUNT(*) as c FROM companies").iloc[0, 0]
print(f"  公司总数: {comp}")
levels = execute_sql("SELECT level, COUNT(*) as c FROM companies GROUP BY level ORDER BY level")
for _, r in levels.iterrows():
    print(f"  层级 {r['level']}: {r['c']} 家")

print("\n" + "=" * 60)
print("3. 科目余额覆盖")
print("=" * 60)
cov = execute_sql("SELECT COUNT(DISTINCT company_code) as c FROM account_balance").iloc[0, 0]
print(f"  有数据的公司: {cov}/{comp}")
periods = execute_sql("SELECT DISTINCT period FROM account_balance ORDER BY period")
print(f"  期间: {periods['period'].tolist()}")

print("\n" + "=" * 60)
print("4. 模板表状态")
print("=" * 60)
for tbl in ["balance_sheet_template", "income_statement_template", "cashflow_template"]:
    try:
        cnt = execute_sql(f"SELECT COUNT(*) as c FROM {tbl}").iloc[0, 0]
        print(f"  {tbl}: {cnt} 行")
    except:
        print(f"  {tbl}: 不存在")

print("\n" + "=" * 60)
print("5. 导入记录统计")
print("=" * 60)
rtype = execute_sql("SELECT report_type, COUNT(*) as c FROM import_logs GROUP BY report_type ORDER BY c DESC")
for _, r in rtype.iterrows():
    print(f"  {r['report_type']}: {r['c']} 条")

print("\n" + "=" * 60)
print("6. 已注册解析器")
print("=" * 60)
from src.import_parser import PARSER_REGISTRY
for k, v in PARSER_REGISTRY.items():
    print(f"  {k} -> {v.TABLE_NAME}")

print("\n" + "=" * 60)
print("7. 报表类型表映射")
print("=" * 60)
from src.models import REPORT_TYPE_TABLE_MAP
for k, v in REPORT_TYPE_TABLE_MAP.items():
    print(f"  {k} -> {v}")

print("\n" + "=" * 60)
print("8. 文件识别模式")
print("=" * 60)
from src.import_parser import FILE_NAME_PATTERNS
for pat, rtype in FILE_NAME_PATTERNS:
    print(f"  {pat} -> {rtype}")

print("\n" + "=" * 60)
print("9. 数据目录文件")
print("=" * 60)
import os
for f in sorted(os.listdir("data")):
    fp = os.path.join("data", f)
    if os.path.isfile(fp):
        size = os.path.getsize(fp)
        print(f"  {f} ({size:,} bytes)")

print("\n" + "=" * 60)
print("10. scripts 目录分类")
print("=" * 60)
scripts = sorted(os.listdir("scripts"))
print(f"  共 {len(scripts)} 个脚本")
for s in scripts:
    with open(os.path.join("scripts", s), encoding="utf-8", errors="ignore") as f:
        first = f.readline().strip()
    print(f"  {s}: {first[:60]}")
