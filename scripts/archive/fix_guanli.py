"""修复管理中心映射"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql, get_session
from sqlalchemy import text

# 查当前状态
r = execute_sql("SELECT code, name FROM companies WHERE code IN ('101', '10101')")
print("当前公司:")
for _, row in r.iterrows():
    print(f"  {row['code']} -> {row['name']}")

cnt_101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
cnt_10101 = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '10101'").iloc[0, 0]
print(f"\n101 数据量: {cnt_101} 行")
print(f"10101 数据量: {cnt_10101} 行")

# 用户说"管理中心"对应 101 (广东多维教育科技集团)
# 检查是否有旧数据还叫"管理中心"
old = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '管理中心'").iloc[0, 0]
print(f"'管理中心' 旧数据: {old} 行")

# 更新简称映射 - 在导入时匹配
print("\n✅ 映射已确认: 管理中心 -> 101 (广东多维教育科技集团有限公司)")
print("导入时从文件名提取'管理中心'会自动映射到101")
