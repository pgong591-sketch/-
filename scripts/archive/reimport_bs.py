"""重新导入资产负债表测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import get_session
from sqlalchemy import text
from src.reports import import_excel_to_db

# 先删旧数据
s = get_session()
s.execute(text("DELETE FROM balance_sheet WHERE company_code='101010136' AND period='202603'"))
s.execute(text("DELETE FROM import_logs WHERE file_name LIKE '%资产负债表%'"))
s.commit()
s.close()
print("旧数据已清理")

# 重新导入
result = import_excel_to_db(
    'data/202603拔创中心(k合01表)合并资产负债表.xls',
    company_code='101010136',
    period='202603',
    original_filename='202603拔创中心(k合01表)合并资产负债表.xls'
)
print(f'导入成功: {result["success"]}, 行数: {result["steps"][-1]["info"]["inserted_rows"]}')
