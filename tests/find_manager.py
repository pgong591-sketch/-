"""搜索管理中心相关数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql

# 搜索所有导入记录
logs = execute_sql("SELECT company_code, period, file_name, status FROM import_logs ORDER BY created_at DESC LIMIT 20")
print("最近20条导入:")
for _, r in logs.iterrows():
    print(f"  [{r['status']}] {r['company_code']:12s} {r['period']} {r['file_name']}")

# 看102的数据（如果"管理中心"映射到了错误编码）
cnt102 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '102'").iloc[0, 0]
cnt101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
cnt10101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '10101'").iloc[0, 0]
print(f"\n101={cnt101}行, 10101={cnt10101}行, 102={cnt102}行")

# 看是否有"管理中心"作为编码
raw = execute_sql("SELECT DISTINCT company_code FROM account_balance WHERE company_code LIKE '%管理%'")
if len(raw) > 0:
    print(f"'管理'编码数据:")
    for _, r in raw.iterrows():
        print(f"  {r['company_code']}")
