"""恢复非学科管理中心的数据到1010101"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql, get_session
from sqlalchemy import text

# 通过文件名找到非学科管理中心的导入批次
logs = execute_sql("SELECT batch_no, file_name, company_code FROM import_logs WHERE file_name LIKE '%非学科%'")
print("非学科管理中心的导入批次:")
for _, r in logs.iterrows():
    print(f"  {r['file_name']} -> batch={r['batch_no']} (当前编码: {r['company_code']})")

# 也找管理中心的导入批次
logs2 = execute_sql("SELECT batch_no, file_name, company_code FROM import_logs WHERE file_name LIKE '%管理中心%' AND file_name NOT LIKE '%非学科%'")
print("\n管理中心的导入批次:")
for _, r in logs2.iterrows():
    print(f"  {r['file_name']} -> batch={r['batch_no']} (当前编码: {r['company_code']})")

all_batches = []
for _, r in logs.iterrows():
    all_batches.append(("非学科", r["batch_no"]))
for _, r in logs2.iterrows():
    all_batches.append(("管理中心", r["batch_no"]))

session = get_session()
total = 0
for label, batch in all_batches:
    cnt = session.execute(
        text("SELECT COUNT(*) FROM account_balance WHERE import_batch = :b AND company_code = '101'"),
        {"b": batch}
    ).scalar()
    if cnt and cnt > 0:
        target = "1010101" if label == "非学科" else "101"
        session.execute(
            text("UPDATE account_balance SET company_code = :target WHERE import_batch = :b AND company_code = '101'"),
            {"target": target, "b": batch}
        )
        # 也修正日志
        session.execute(
            text("UPDATE import_logs SET company_code = :target WHERE batch_no = :b"),
            {"target": target, "b": batch}
        )
        print(f"  {label}批次 {batch}: 恢复 {cnt} 行到 {target}")
        total += cnt
    else:
        print(f"  {label}批次 {batch}: 无数据在101中")

session.commit()
session.close()
print(f"\n✅ 共恢复 {total} 行")

# 验证
cnt_101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
cnt_1010101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '1010101'").iloc[0, 0]
print(f"\n101 (广东多维): {cnt_101} 行")
print(f"1010101 (东莞非学科管理中心): {cnt_1010101} 行")
