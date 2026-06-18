"""检查101下重复科目"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 重复科目
df = execute_sql("""
    SELECT account_code, account_name, assist_dimensions,
           COUNT(*) as cnt, SUM(opening_balance) as op,
           SUM(debit_amount) as dr, SUM(credit_amount) as cr,
           SUM(ending_balance) as end
    FROM account_balance
    WHERE company_code = '101' AND period = '202603'
    GROUP BY account_code
    HAVING cnt > 1
    ORDER BY cnt DESC
""")
print(f"101 重复科目 ({len(df)} 个):")
for _, r in df.head(5).iterrows():
    print(f"  {r['account_code']:8s} {str(r['account_name']):20s} cnt={r['cnt']}")

# 看具体的重复行
if len(df) > 0:
    acct = df.iloc[0]["account_code"]
    print(f"\n科目 {acct} 的详细行:")
    rows = execute_sql(f"SELECT account_code, account_name, assist_dimensions, debit_amount, credit_amount, ending_balance FROM account_balance WHERE company_code = '101' AND period = '202603' AND account_code = '{acct}'")
    for _, r in rows.iterrows():
        print(f"  ad={str(r['assist_dimensions'])[:30]:30s} dr={r['debit_amount']:>10.2f} cr={r['credit_amount']:>10.2f} end={r['ending_balance']:>10.2f}")
