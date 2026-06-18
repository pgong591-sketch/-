"""检查负债合计行的数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

# 检查负债合计的具体数据
df = execute_sql("""
    SELECT side, item_name, line_number, ending_balance, opening_balance, is_subtotal, sort_order
    FROM balance_sheet
    WHERE company_code='101010136' AND period='202603'
      AND (item_name LIKE '%负债合计%' OR item_name LIKE '%所有者权益%')
    ORDER BY sort_order
""")
print("=== 负债合计行数据 ===")
print(df.to_string(index=False))

# 检查所有出现 None 或 NaN 的行
df2 = execute_sql("""
    SELECT side, item_name, ending_balance, opening_balance, sort_order
    FROM balance_sheet
    WHERE company_code='101010136' AND period='202603'
      AND (ending_balance IS NULL OR opening_balance IS NULL
           OR ending_balance != ending_balance OR opening_balance != opening_balance)
    ORDER BY sort_order
""")
print(f"\n=== 含 NULL/NaN 的行: {len(df2)} 行 ===")
if len(df2) > 0:
    print(df2.to_string(index=False))
else:
    print("(无)")
