"""修复拔创中心数据编码"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session, execute_sql
from sqlalchemy import text

session = get_session()
session.execute(text("UPDATE account_balance SET company_code = '101010136' WHERE company_code = '拔创中心'"))
session.commit()
session.close()

# 验证
cnt = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101010136'")
print(f"101010136 数据量: {cnt.iloc[0,0]} 行")
left = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code LIKE '%拔创%'")
print(f"残留中文编码: {left.iloc[0,0]} 行")
