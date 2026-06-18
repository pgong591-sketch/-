"""查看以前年度损益调整科目详情"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

df = execute_sql("""
    SELECT account_code, account_name, assist_dimensions,
           opening_balance, debit_amount, credit_amount, ending_balance, direction
    FROM account_balance
    WHERE company_code = '101' AND period = '202603'
      AND account_name LIKE '%以前年度%'
""")
print(f"共 {len(df)} 行:")
for _, r in df.iterrows():
    dim = str(r["assist_dimensions"])[:40] if r["assist_dimensions"] else "(空)"
    print(f"  科目={r['account_code']:8s} {str(r['account_name']):20s}")
    print(f"  辅助核算={dim}")
    print(f"  期初={r['opening_balance']:>12.2f} 借方={r['debit_amount']:>12.2f} 贷方={r['credit_amount']:>12.2f} 期末={r['ending_balance']:>12.2f}")
    print()
