"""清理资产负债表中的section标题行"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import get_session
from sqlalchemy import text

s = get_session()
r = s.execute(text(
    "DELETE FROM balance_sheet WHERE item_name IN ('所有者权益（或股东权益）','非流动资产')"
))
s.commit()
print(f"删除了 {r.rowcount} 行 section 标题")

# 验证
import pandas as pd
cnt = pd.read_sql("SELECT COUNT(*) as c FROM balance_sheet WHERE company_code='101010136' AND period='202603'", s.connection())
print(f"剩余 {cnt.iloc[0,0]} 行")
s.close()
