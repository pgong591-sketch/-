"""清理并重新导入损益表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import get_session
from sqlalchemy import text

s = get_session()
s.execute(text("DELETE FROM income_statement"))
s.execute(text("DELETE FROM import_logs WHERE report_type='income_statement'"))
s.commit()
s.close()
print("已清理")

from src.reports import import_excel_to_db
r = import_excel_to_db('data/损益表.xlsx', period='202603', original_filename='202603损益表.xlsx')
print(f'导入: {r["success"]}, 行数: {r["steps"][-1]["info"]["total_rows"]}')
