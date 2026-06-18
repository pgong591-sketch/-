"""清理 account_balance 中的重复行（同公司+同期+同科目+同辅助核算）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session, execute_sql
from sqlalchemy import text

# 找出所有重复行并按期初/借方/贷方/期末求和
session = get_session()

# 处理方式：对重复行按(company_code, period, account_code, assist_dimensions)分组，
# 取各项金额的SUM，保留一条，删除其他
rows = session.execute(text("""
    SELECT rowid, company_code, period, account_code, assist_dimensions,
           opening_balance, debit_amount, credit_amount, ending_balance, direction
    FROM account_balance
    WHERE (company_code, period, account_code, COALESCE(assist_dimensions, '')) IN (
        SELECT company_code, period, account_code, COALESCE(assist_dimensions, '')
        FROM account_balance
        GROUP BY company_code, period, account_code, COALESCE(assist_dimensions, '')
        HAVING COUNT(*) > 1
    )
    ORDER BY company_code, period, account_code, assist_dimensions
""")).fetchall()

print(f"发现 {len(rows)} 行重复数据需要清理")

if len(rows) == 0:
    print("✅ 无重复数据")
    session.close()
    exit()

# 分组处理
from collections import defaultdict
groups = defaultdict(list)
for r in rows:
    key = (r[1], r[2], r[3], r[4])  # (company, period, account, assist)
    groups[key].append(r)

cleaned = 0
for key, group in groups.items():
    # 保留第一行，用合计值更新
    first = group[0]
    total_op = sum(r[5] for r in group)
    total_dr = sum(r[6] for r in group)
    total_cr = sum(r[7] for r in group)
    total_end = sum(r[8] for r in group)
    direction = group[0][9]  # 用第一条的方向

    # 更新第一行
    session.execute(
        text("UPDATE account_balance SET opening_balance=:op, debit_amount=:dr, credit_amount=:cr, ending_balance=:end, direction=:dir WHERE rowid=:rid"),
        {"op": total_op, "dr": total_dr, "cr": total_cr, "end": total_end, "dir": direction, "rid": first[0]}
    )

    # 删除其余行
    for r in group[1:]:
        session.execute(text("DELETE FROM account_balance WHERE rowid=:rid"), {"rid": r[0]})
        cleaned += 1

session.commit()
session.close()

print(f"✅ 已清理 {cleaned} 行重复数据")

# 验证
remaining = execute_sql("""
    SELECT COUNT(*) as cnt FROM (
        SELECT company_code, period, account_code, COALESCE(assist_dimensions, '')
        FROM account_balance
        GROUP BY company_code, period, account_code, COALESCE(assist_dimensions, '')
        HAVING COUNT(*) > 1
    )
""").iloc[0, 0]
print(f"剩余重复分组: {remaining}")
if remaining == 0:
    print("✅ 无重复数据")
