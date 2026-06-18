"""修复管理中心数据到101"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session, execute_sql
from sqlalchemy import text

# 先看1010101有多少数据
old = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '1010101'").iloc[0, 0]
print(f"1010101 (旧管理中心): {old} 行")

if old > 0:
    session = get_session()
    session.execute(text("DELETE FROM account_balance WHERE company_code = '101'"))
    session.execute(text("UPDATE account_balance SET company_code = '101' WHERE company_code = '1010101'"))
    # 同时更新导入日志
    session.execute(text("UPDATE import_logs SET company_code = '101' WHERE company_code = '1010101'"))
    session.commit()
    session.close()
    
    new = execute_sql("SELECT COUNT(*) as cnt FROM account_balance WHERE company_code = '101'").iloc[0, 0]
    print(f"101 (广东多维) 现有: {new} 行")
else:
    print("1010101 无数据，无需迁移")
