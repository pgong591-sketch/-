"""验证清理结果"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db_connection import execute_sql

# 查是否还有脏数据
for kw in ["科目编码", "科目名称", "制单", "打印"]:
    df = execute_sql(
        "SELECT account_code, account_name, company_code FROM account_balance "
        "WHERE account_code LIKE :p OR account_name LIKE :p LIMIT 3",
        {"p": f"%{kw}%"}
    )
    if len(df) > 0:
        print(f"'{kw}' 残留: {len(df)} 行")
        print(df.to_string(index=False))
    else:
        print(f"'{kw}' ✅ 已清空")
