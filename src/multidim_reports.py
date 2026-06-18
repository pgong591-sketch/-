"""Fixed-format management reports used by the multidimensional table pages."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .company_hierarchy import get_company_list_for_summary
from .dashboard_metrics import INCOME_ITEM, NET_PROFIT_ITEM
from .db_connection import execute_sql


SUMMARY_ITEMS = [
    "一、营业收入",
    "减：营业成本",
    "税金及附加",
    "销售费用",
    "管理费用",
    "财务费用",
    "加：投资收益（损失以“-”号填列）",
    "二、营业利润（亏损以“-”号填列）",
    "加：营业外收入",
    "减：营业外支出",
    "四、净利润（净亏损以“-”号填列）",
]


def get_multidim_income_statement(
    period: str,
    scope_code: Optional[str] = None,
    company_codes: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Return a fixed-format income statement with companies as columns."""
    df = _income_rows(period, scope_code, company_codes)
    if len(df) == 0:
        return pd.DataFrame()

    pivot = df.pivot_table(
        index=["sort_order", "item_name"],
        columns="company_name",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    )
    pivot["合计"] = pivot.sum(axis=1)
    pivot = pivot.reset_index().sort_values("sort_order")
    pivot = pivot.drop(columns=["sort_order"]).rename(columns={"item_name": "项目"})
    return pivot


def get_operating_summary(
    period: str,
    scope_code: Optional[str] = None,
    company_codes: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Return the operating summary table used by the fixed-format page."""
    df = _income_rows(period, scope_code, company_codes)
    if len(df) == 0:
        return pd.DataFrame()

    by_item = df.groupby("item_name")["amount"].sum().to_dict()
    revenue = _num(by_item.get(INCOME_ITEM))
    cost = _num(by_item.get("减：营业成本"))
    gross_profit = revenue - cost
    expense_total = sum(
        _num(by_item.get(item))
        for item in ["税金及附加", "销售费用", "管理费用", "财务费用"]
    )
    net_profit = _num(by_item.get(NET_PROFIT_ITEM))

    rows = [
        ("营业收入", revenue, _safe_div(revenue, revenue), "收入规模"),
        ("营业成本", cost, _safe_div(cost, revenue), "直接成本"),
        ("毛利", gross_profit, _safe_div(gross_profit, revenue), "收入-成本"),
        ("费用合计", expense_total, _safe_div(expense_total, revenue), "税金、销售、管理、财务费用"),
        ("营业利润", _num(by_item.get("二、营业利润（亏损以“-”号填列）")), _safe_div(by_item.get("二、营业利润（亏损以“-”号填列）"), revenue), "经营利润"),
        ("净利润", net_profit, _safe_div(net_profit, revenue), "最终经营结果"),
    ]
    return pd.DataFrame(rows, columns=["项目", "金额", "占收入比", "说明"])


def get_picture_brief_sections(period: str, dashboard: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """Build compact tables for the picture brief page from dashboard data."""
    budget = dashboard.get("budget", {})
    income = dashboard.get("income", {})
    balance = dashboard.get("balance", {})
    completeness = dashboard.get("import_completeness", {})

    overview = pd.DataFrame([
        ["期间", period],
        ["本月收入", _num(income.get("revenue"))],
        ["本月净利润", _num(income.get("net_profit"))],
        ["净利率", _safe_div(income.get("net_profit"), income.get("revenue"))],
        ["货币资金", _num(balance.get("cash"))],
        ["预收账款", _num(balance.get("advance_receipts"))],
    ], columns=["指标", "值"])

    budget_table = pd.DataFrame([
        ["收入", _num(budget.get("income_actual_ytd")), _num(budget.get("income_target")), budget.get("income_completion")],
        ["利润", _num(budget.get("profit_actual_ytd")), _num(budget.get("profit_target")), budget.get("profit_completion")],
    ], columns=["类型", "本年累计", "年度目标", "完成率"])

    import_table = pd.DataFrame([
        [name, count, completeness.get("expected_company_count", 0)]
        for name, count in completeness.get("by_report", {}).items()
    ], columns=["报表", "已导入公司数", "参考公司数"])

    return {"经营概览": overview, "预算完成": budget_table, "导入完整性": import_table}


def _income_rows(
    period: str,
    scope_code: Optional[str],
    company_codes: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    params: Dict[str, Any] = {"period": period}
    scope_sql = _scope_filter("i", scope_code, params, company_codes)
    item_sql = _bind_in_clause("i.item_name", SUMMARY_ITEMS, params, "summary_item")
    return execute_sql(
        f"""
        SELECT
            i.item_name,
            i.sort_order,
            i.period1_value AS amount,
            i.company_code,
            COALESCE(c.short_name, c.name, i.company_code) AS company_name
        FROM income_statement i
        LEFT JOIN companies c ON i.company_code = c.code
        WHERE i.period = :period
          AND {item_sql}
          {scope_sql}
        ORDER BY i.sort_order, i.item_name, company_name
        """,
        params,
    )


def _scope_filter(
    alias: str,
    scope_code: Optional[str],
    params: Dict[str, Any],
    company_codes: Optional[Sequence[str]] = None,
) -> str:
    if company_codes is not None:
        codes = [str(code) for code in company_codes if str(code)]
        return f" AND {_bind_in_clause(f'{alias}.company_code', codes, params, 'scope_company')}"

    if not scope_code:
        return f"""
          AND {alias}.company_code IN (
              SELECT code FROM companies
              WHERE status = 1 AND is_consolidated = 1
          )
        """

    codes = get_company_list_for_summary(scope_code)
    if not codes:
        codes = [scope_code]
    return f" AND {_bind_in_clause(f'{alias}.company_code', codes, params, 'scope_company')}"


def _bind_in_clause(
    column: str,
    values: List[Any],
    params: Dict[str, Any],
    prefix: str,
) -> str:
    if not values:
        return "1 = 0"
    placeholders = []
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        params[key] = str(value)
        placeholders.append(f":{key}")
    return f"{column} IN ({', '.join(placeholders)})"


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except TypeError:
        pass
    return float(value)


def _safe_div(numerator: Any, denominator: Any) -> Optional[float]:
    denominator = _num(denominator)
    if denominator == 0:
        return None
    return _num(numerator) / denominator
