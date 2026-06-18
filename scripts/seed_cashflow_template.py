"""Seed the default cashflow template.

The current project does not yet have confirmed cashflow item-to-account
mapping. This seed creates a conservative template with standard sections and
cash-equivalent checks based on account codes 1001/1002.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from src.db_connection import get_session


SQL_EXPR = "SQL表达式"
FIXED_VALUE = "固定值"

CASH_ACCOUNT_FILTER = """
(
    account_code LIKE '1001%'
    OR account_code LIKE '1002%'
)
"""

ROWS = [
    (1, "一、经营活动产生的现金流量", "经营活动", 2, FIXED_VALUE, "0", None, "+", 0, 1, 10),
    (2, "销售商品、提供劳务收到的现金", "经营活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 20),
    (3, "收到的其他与经营活动有关的现金", "经营活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 30),
    (4, "经营活动现金流入小计", "经营活动", 1, FIXED_VALUE, "0", None, "+", 1, 1, 40),
    (5, "购买商品、接受劳务支付的现金", "经营活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 50),
    (6, "支付给职工以及为职工支付的现金", "经营活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 60),
    (7, "支付的各项税费", "经营活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 70),
    (8, "支付的其他与经营活动有关的现金", "经营活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 80),
    (9, "经营活动现金流出小计", "经营活动", 1, FIXED_VALUE, "0", None, "-", 1, 1, 90),
    (10, "经营活动产生的现金流量净额", "经营活动", 1, FIXED_VALUE, "0", None, "+", 0, 1, 100),
    (11, "二、投资活动产生的现金流量", "投资活动", 2, FIXED_VALUE, "0", None, "+", 0, 1, 110),
    (12, "收回投资收到的现金", "投资活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 120),
    (13, "取得投资收益收到的现金", "投资活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 130),
    (14, "处置固定资产、无形资产和其他长期资产收回的现金净额", "投资活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 140),
    (15, "投资活动现金流入小计", "投资活动", 1, FIXED_VALUE, "0", None, "+", 1, 1, 150),
    (16, "购建固定资产、无形资产和其他长期资产支付的现金", "投资活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 160),
    (17, "投资支付的现金", "投资活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 170),
    (18, "投资活动现金流出小计", "投资活动", 1, FIXED_VALUE, "0", None, "-", 1, 1, 180),
    (19, "投资活动产生的现金流量净额", "投资活动", 1, FIXED_VALUE, "0", None, "+", 0, 1, 190),
    (20, "三、筹资活动产生的现金流量", "筹资活动", 2, FIXED_VALUE, "0", None, "+", 0, 1, 200),
    (21, "吸收投资收到的现金", "筹资活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 210),
    (22, "取得借款收到的现金", "筹资活动", 0, FIXED_VALUE, "0", None, "+", 1, 0, 220),
    (23, "筹资活动现金流入小计", "筹资活动", 1, FIXED_VALUE, "0", None, "+", 1, 1, 230),
    (24, "偿还债务支付的现金", "筹资活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 240),
    (25, "分配股利、利润或偿付利息支付的现金", "筹资活动", 0, FIXED_VALUE, "0", None, "-", 1, 0, 250),
    (26, "筹资活动现金流出小计", "筹资活动", 1, FIXED_VALUE, "0", None, "-", 1, 1, 260),
    (27, "筹资活动产生的现金流量净额", "筹资活动", 1, FIXED_VALUE, "0", None, "+", 0, 1, 270),
    (28, "四、现金及现金等价物净增加额", "现金及现金等价物", 1, SQL_EXPR, None,
     f"SELECT COALESCE(SUM(debit_amount - credit_amount), 0) FROM account_balance WHERE company_code = :company AND period = :period AND {CASH_ACCOUNT_FILTER}",
     "+", 0, 1, 280),
    (29, "加：期初现金及现金等价物余额", "现金及现金等价物", 0, SQL_EXPR, None,
     f"SELECT COALESCE(SUM(opening_balance), 0) FROM account_balance WHERE company_code = :company AND period = :period AND {CASH_ACCOUNT_FILTER}",
     "+", 0, 0, 290),
    (30, "五、期末现金及现金等价物余额", "现金及现金等价物", 1, SQL_EXPR, None,
     f"SELECT COALESCE(SUM(ending_balance), 0) FROM account_balance WHERE company_code = :company AND period = :period AND {CASH_ACCOUNT_FILTER}",
     "+", 0, 1, 300),
]


def seed_cashflow_template(replace: bool = False) -> int:
    session = get_session()
    try:
        if replace:
            session.execute(text("DELETE FROM cashflow_template"))
        existing = session.execute(text("SELECT COUNT(*) FROM cashflow_template")).scalar() or 0
        if existing and not replace:
            return 0

        for row in ROWS:
            session.execute(text("""
                INSERT INTO cashflow_template
                    (line_no, item_name, cf_category, is_subtotal, formula_type,
                     account_ranges, sql_expression, sign, indent_level, is_bold, sort_order)
                VALUES
                    (:line_no, :item_name, :cf_category, :is_subtotal, :formula_type,
                     :account_ranges, :sql_expression, :sign, :indent_level, :is_bold, :sort_order)
            """), {
                "line_no": row[0],
                "item_name": row[1],
                "cf_category": row[2],
                "is_subtotal": row[3],
                "formula_type": row[4],
                "account_ranges": row[5],
                "sql_expression": row[6],
                "sign": row[7],
                "indent_level": row[8],
                "is_bold": row[9],
                "sort_order": row[10],
            })
        session.commit()
        return len(ROWS)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="replace existing cashflow template rows")
    args = parser.parse_args()
    inserted = seed_cashflow_template(replace=args.replace)
    print(f"cashflow_template seeded rows: {inserted}")


if __name__ == "__main__":
    main()
