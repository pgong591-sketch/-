"""Dashboard metric service for the Streamlit home page."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .budget_importer import ensure_budget_tables
from .company_hierarchy import get_company_list_for_summary
from .db_connection import execute_sql


INCOME_ITEM = "一、营业收入"
NET_PROFIT_ITEM = "四、净利润（净亏损以“-”号填列）"
COST_ITEMS = [
    "减：营业成本",
    "税金及附加",
    "销售费用",
    "管理费用",
    "财务费用",
]


def get_dashboard_periods() -> List[str]:
    """Return available reporting periods for dashboard selectors."""
    frames = []
    for table in ["income_statement", "balance_sheet", "account_balance"]:
        try:
            frames.append(execute_sql(f"SELECT DISTINCT period FROM {table} WHERE period IS NOT NULL"))
        except Exception:
            continue
    if not frames:
        return []
    periods = pd.concat(frames, ignore_index=True)["period"].dropna().astype(str).unique()
    return sorted(periods.tolist(), reverse=True)


def get_home_dashboard(
    period: str,
    scope_code: Optional[str] = None,
    explicit_company_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build all homepage dashboard sections from normalized warehouse facts.

    Ratio metrics are recalculated from source amounts instead of summing ratio
    rows from imported spreadsheets.
    """
    ensure_budget_tables()
    if explicit_company_codes is not None:
        company_codes = _filter_consolidated_codes(explicit_company_codes)
    else:
        company_codes = _scope_company_codes(scope_code)
    year = str(period)[:4]
    month = int(str(period)[4:6])

    income = _income_summary(period, company_codes)
    balance = _balance_summary(period, company_codes)
    budget = _budget_summary(year, month, company_codes if scope_code else None, company_codes)
    funds = _funds_by_company(period, company_codes)
    ranking = _company_ranking(period, company_codes)
    completeness = _import_completeness(period, company_codes)
    anomalies = _build_anomalies(balance, funds, ranking)

    revenue = income["revenue"]
    net_profit = income["net_profit"]
    net_margin = _safe_div(net_profit, revenue)
    available_funds = (
        balance["cash"] + balance["other_receivables"] - balance["other_payables"]
    )
    cost_run_rate = income["cost_run_rate"]
    cash_turnover_months = _safe_div(available_funds, cost_run_rate)

    return {
        "period": period,
        "scope_code": scope_code,
        "scope_company_count": len(company_codes),
        "kpis": [
            _kpi("本月收入", revenue, "money", budget.get("income_completion")),
            _kpi("本月净利润", net_profit, "money", net_margin),
            _kpi("净利率", net_margin, "percent", None),
            _kpi("收入年度完成率", budget.get("income_completion"), "percent", None),
            _kpi("利润年度完成率", budget.get("profit_completion"), "percent", None),
            _kpi("货币资金", balance["cash"], "money", cash_turnover_months),
            _kpi("预收账款", balance["advance_receipts"], "money", None),
            _kpi("资产负债平衡差", balance["balance_gap"], "money", None),
        ],
        "income": income,
        "balance": balance,
        "budget": budget,
        "funds": funds,
        "ranking": ranking,
        "import_completeness": completeness,
        "anomalies": anomalies,
    }


def _kpi(label: str, value: Any, value_type: str, delta: Any) -> Dict[str, Any]:
    return {"label": label, "value": value, "type": value_type, "delta": delta}


def _scope_company_codes(scope_code: Optional[str]) -> List[str]:
    if scope_code:
        codes = get_company_list_for_summary(scope_code)
        if not codes:
            return [scope_code]
        return _filter_consolidated_codes(codes)

    df = execute_sql("""
        SELECT code
        FROM companies
        WHERE status = 1 AND is_consolidated = 1
        ORDER BY tree_path, code
    """)
    return df["code"].astype(str).tolist() if len(df) else []


def _filter_consolidated_codes(codes: Iterable[str]) -> List[str]:
    codes = [str(code) for code in codes if code]
    if not codes:
        return []
    params = {f"c{i}": code for i, code in enumerate(codes)}
    placeholders = ", ".join([f":c{i}" for i in range(len(codes))])
    df = execute_sql(
        f"""
        SELECT code
        FROM companies
        WHERE status = 1 AND is_consolidated = 1 AND code IN ({placeholders})
        """,
        params,
    )
    return df["code"].astype(str).tolist() if len(df) else []


def _company_filter(alias: str, company_codes: List[str], params: Dict[str, Any]) -> str:
    if not company_codes:
        return " AND 1 = 0"
    placeholders = []
    for idx, code in enumerate(company_codes):
        key = f"{alias}_company_{idx}"
        params[key] = code
        placeholders.append(f":{key}")
    return f" AND {alias}.company_code IN ({', '.join(placeholders)})"


def _income_summary(period: str, company_codes: List[str]) -> Dict[str, float]:
    params: Dict[str, Any] = {"period": period}
    company_sql = _company_filter("i", company_codes, params)
    df = execute_sql(
        f"""
        SELECT
            SUM(CASE WHEN item_name = :income_item THEN period1_value ELSE 0 END) AS revenue,
            SUM(CASE WHEN item_name = :profit_item THEN period1_value ELSE 0 END) AS net_profit,
            SUM(CASE WHEN item_name IN (:cost1, :cost2, :cost3, :cost4, :cost5)
                     THEN period1_value ELSE 0 END) AS cost_run_rate
        FROM income_statement i
        WHERE period = :period {company_sql}
        """,
        {
            **params,
            "income_item": INCOME_ITEM,
            "profit_item": NET_PROFIT_ITEM,
            "cost1": COST_ITEMS[0],
            "cost2": COST_ITEMS[1],
            "cost3": COST_ITEMS[2],
            "cost4": COST_ITEMS[3],
            "cost5": COST_ITEMS[4],
        },
    )
    row = df.iloc[0].to_dict() if len(df) else {}
    revenue = _num(row.get("revenue"))
    net_profit = _num(row.get("net_profit"))
    cost_run_rate = abs(_num(row.get("cost_run_rate")))
    return {
        "revenue": revenue,
        "net_profit": net_profit,
        "net_margin": _safe_div(net_profit, revenue),
        "cost_run_rate": cost_run_rate,
    }


def _balance_summary(period: str, company_codes: List[str]) -> Dict[str, float]:
    params: Dict[str, Any] = {"period": period}
    company_sql = _company_filter("b", company_codes, params)
    df = execute_sql(
        f"""
        SELECT
            SUM(CASE WHEN item_name = '货币资金' THEN ending_balance ELSE 0 END) AS cash,
            SUM(CASE WHEN item_name = '预收账款' THEN ending_balance ELSE 0 END) AS advance_receipts,
            SUM(CASE WHEN item_name = '其他应收款' THEN ending_balance ELSE 0 END) AS other_receivables,
            SUM(CASE WHEN item_name = '其他应付款' THEN ending_balance ELSE 0 END) AS other_payables,
            SUM(CASE WHEN item_name = '资产总计' THEN ending_balance ELSE 0 END) AS total_assets,
            SUM(CASE WHEN item_name = '负债和所有者权益（或股东权益）总计' THEN ending_balance ELSE 0 END) AS total_liabilities_equity
        FROM balance_sheet b
        WHERE period = :period {company_sql}
        """,
        params,
    )
    row = df.iloc[0].to_dict() if len(df) else {}
    total_assets = _num(row.get("total_assets"))
    total_liabilities_equity = _num(row.get("total_liabilities_equity"))
    return {
        "cash": _num(row.get("cash")),
        "advance_receipts": _num(row.get("advance_receipts")),
        "other_receivables": _num(row.get("other_receivables")),
        "other_payables": _num(row.get("other_payables")),
        "total_assets": total_assets,
        "total_liabilities_equity": total_liabilities_equity,
        "balance_gap": total_assets - total_liabilities_equity,
    }


def _budget_summary(
    year: str,
    month: int,
    target_company_codes: Optional[List[str]],
    fact_company_codes: List[str],
) -> Dict[str, Any]:
    income_target = _budget_target_total(year, "income", target_company_codes)
    profit_target = _budget_target_total(year, "profit", target_company_codes)
    income_actual = _actual_ytd(year, month, "income", target_company_codes, fact_company_codes)
    profit_actual = _actual_ytd(year, month, "profit", target_company_codes, fact_company_codes)
    progress = _budget_progress(year, month, target_company_codes, fact_company_codes)

    return {
        "year": year,
        "income_target": income_target,
        "profit_target": profit_target,
        "income_actual_ytd": income_actual,
        "profit_actual_ytd": profit_actual,
        "income_completion": _safe_div(income_actual, income_target),
        "profit_completion": _safe_div(profit_actual, profit_target),
        "theory_completion": month / 12,
        "progress": progress,
    }


def _budget_target_total(year: str, target_type: str, company_codes: Optional[List[str]]) -> float:
    params: Dict[str, Any] = {"year": year, "target_type": target_type}
    filter_sql = ""
    if company_codes is not None:
        filter_sql = _budget_company_filter("company_code", company_codes, params)
    df = execute_sql(
        f"""
        SELECT SUM(annual_target) AS amount
        FROM budget_targets
        WHERE budget_year = :year AND target_type = :target_type {filter_sql}
        """,
        params,
    )
    return _num(df.iloc[0]["amount"]) if len(df) else 0.0


def _actual_ytd(
    year: str,
    month: int,
    metric_type: str,
    target_company_codes: Optional[List[str]],
    fact_company_codes: List[str],
) -> float:
    warehouse = _warehouse_actuals_by_period(year, month, metric_type, fact_company_codes)
    overrides = _override_actuals_by_period(year, month, metric_type, target_company_codes)
    total = 0.0
    for current_month in range(1, month + 1):
        period = f"{year}{current_month:02d}"
        if period in warehouse:
            total += warehouse[period]
        else:
            total += overrides.get(period, 0.0)
    return total


def _warehouse_actuals_by_period(
    year: str,
    month: int,
    metric_type: str,
    company_codes: List[str],
) -> Dict[str, float]:
    item = INCOME_ITEM if metric_type == "income" else NET_PROFIT_ITEM
    params: Dict[str, Any] = {
        "start": f"{year}01",
        "end": f"{year}{month:02d}",
        "item": item,
    }
    company_sql = _company_filter("i", company_codes, params)
    df = execute_sql(
        f"""
        SELECT period, SUM(period1_value) AS amount
        FROM income_statement i
        WHERE period BETWEEN :start AND :end AND item_name = :item {company_sql}
        GROUP BY period
        """,
        params,
    )
    return {str(row["period"]): _num(row["amount"]) for _, row in df.iterrows()}


def _override_actuals_by_period(
    year: str,
    month: int,
    metric_type: str,
    company_codes: Optional[List[str]],
) -> Dict[str, float]:
    params: Dict[str, Any] = {
        "year": year,
        "start": f"{year}01",
        "end": f"{year}{month:02d}",
        "metric_type": metric_type,
    }
    filter_sql = ""
    if company_codes is not None:
        filter_sql = _budget_company_filter("company_code", company_codes, params)
    df = execute_sql(
        f"""
        SELECT period, SUM(amount) AS amount
        FROM budget_actual_overrides
        WHERE budget_year = :year
          AND period BETWEEN :start AND :end
          AND metric_type = :metric_type
          {filter_sql}
        GROUP BY period
        """,
        params,
    )
    return {str(row["period"]): _num(row["amount"]) for _, row in df.iterrows()}


def _budget_company_filter(column: str, company_codes: List[str], params: Dict[str, Any]) -> str:
    if not company_codes:
        return " AND 1 = 0"
    placeholders = []
    for idx, code in enumerate(company_codes):
        key = f"budget_company_{idx}"
        params[key] = code
        placeholders.append(f":{key}")
    return f" AND {column} IN ({', '.join(placeholders)})"


def _budget_progress(
    year: str,
    month: int,
    target_company_codes: Optional[List[str]],
    fact_company_codes: List[str],
) -> pd.DataFrame:
    params: Dict[str, Any] = {"year": year}
    filter_sql = ""
    if target_company_codes is not None:
        filter_sql = _budget_company_filter("company_code", target_company_codes, params)
    targets = execute_sql(
        f"""
        SELECT module, project, company_code, target_type, annual_target
        FROM budget_targets
        WHERE budget_year = :year {filter_sql}
        ORDER BY module, project, target_type
        """,
        params,
    )
    if len(targets) == 0:
        return pd.DataFrame()

    rows = []
    for _, row in targets.iterrows():
        code = row.get("company_code")
        code_filter = [str(code)] if pd.notna(code) and str(code) else fact_company_codes
        actual = _actual_ytd(year, month, row["target_type"], code_filter, code_filter)
        target = _num(row["annual_target"])
        rows.append({
            "模块": row.get("module", ""),
            "项目": row.get("project", ""),
            "类型": "收入" if row["target_type"] == "income" else "利润",
            "年度目标": target,
            "本年累计": actual,
            "完成率": _safe_div(actual, target),
            "偏离理论进度": _safe_div(actual, target) - month / 12 if target else None,
        })
    return pd.DataFrame(rows)


def _funds_by_company(period: str, company_codes: List[str]) -> pd.DataFrame:
    params: Dict[str, Any] = {"period": period}
    company_sql = _company_filter("b", company_codes, params)
    df = execute_sql(
        f"""
        SELECT
            b.company_code AS 公司编码,
            COALESCE(c.short_name, c.name, b.company_code) AS 公司,
            SUM(CASE WHEN b.item_name = '货币资金' THEN b.ending_balance ELSE 0 END) AS 货币资金,
            SUM(CASE WHEN b.item_name = '其他应收款' THEN b.ending_balance ELSE 0 END) AS 其他应收款,
            SUM(CASE WHEN b.item_name = '其他应付款' THEN b.ending_balance ELSE 0 END) AS 其他应付款,
            SUM(CASE WHEN b.item_name = '预收账款' THEN b.ending_balance ELSE 0 END) AS 预收账款,
            SUM(CASE WHEN b.item_name = '资产总计' THEN b.ending_balance ELSE 0 END) AS 资产总计,
            SUM(CASE WHEN b.item_name = '负债和所有者权益（或股东权益）总计' THEN b.ending_balance ELSE 0 END) AS 负债权益总计
        FROM balance_sheet b
        LEFT JOIN companies c ON b.company_code = c.code
        WHERE b.period = :period {company_sql}
        GROUP BY b.company_code, COALESCE(c.short_name, c.name, b.company_code)
        """,
        params,
    )
    if len(df) == 0:
        return df
    df["可使用周转金"] = df["货币资金"] + df["其他应收款"] - df["其他应付款"]
    df["平衡差"] = df["资产总计"] - df["负债权益总计"]
    return df.sort_values("可使用周转金")


def _company_ranking(period: str, company_codes: List[str]) -> pd.DataFrame:
    params: Dict[str, Any] = {
        "period": period,
        "income_item": INCOME_ITEM,
        "profit_item": NET_PROFIT_ITEM,
    }
    company_sql = _company_filter("i", company_codes, params)
    df = execute_sql(
        f"""
        SELECT
            i.company_code AS 公司编码,
            COALESCE(c.short_name, c.name, i.company_code) AS 公司,
            SUM(CASE WHEN i.item_name = :income_item THEN i.period1_value ELSE 0 END) AS 收入,
            SUM(CASE WHEN i.item_name = :profit_item THEN i.period1_value ELSE 0 END) AS 净利润
        FROM income_statement i
        LEFT JOIN companies c ON i.company_code = c.code
        WHERE i.period = :period {company_sql}
        GROUP BY i.company_code, COALESCE(c.short_name, c.name, i.company_code)
        """,
        params,
    )
    if len(df) == 0:
        return df
    df["净利率"] = df.apply(lambda row: _safe_div(row["净利润"], row["收入"]), axis=1)
    return df.sort_values("收入", ascending=False)


def _import_completeness(period: str, company_codes: List[str]) -> Dict[str, Any]:
    tables = {
        "科目余额": "account_balance",
        "资产负债表": "balance_sheet",
        "损益表": "income_statement",
    }
    counts = {}
    for label, table in tables.items():
        params: Dict[str, Any] = {"period": period}
        company_sql = _company_filter("f", company_codes, params)
        df = execute_sql(
            f"""
            SELECT COUNT(DISTINCT f.company_code) AS company_count
            FROM {table} f
            WHERE f.period = :period {company_sql}
            """,
            params,
        )
        counts[label] = int(_num(df.iloc[0]["company_count"])) if len(df) else 0

    expected = max([1] + list(counts.values()))
    score = sum(_safe_div(value, expected) for value in counts.values()) / len(counts)
    return {
        "expected_company_count": expected,
        "by_report": counts,
        "score": score,
    }


def _build_anomalies(balance: Dict[str, float], funds: pd.DataFrame, ranking: pd.DataFrame) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []
    if abs(balance.get("balance_gap", 0.0)) > 1:
        anomalies.append({
            "级别": "预警",
            "项目": "资产负债平衡",
            "说明": f"集团资产负债平衡差为 {balance['balance_gap']:,.2f}",
        })
    if len(funds) > 0:
        for _, row in funds.head(5).iterrows():
            if _num(row.get("可使用周转金")) < 0:
                anomalies.append({
                    "级别": "预警",
                    "项目": row.get("公司", ""),
                    "说明": f"可使用周转金为 {row['可使用周转金']:,.2f}",
                })
    if len(ranking) > 0:
        loss_rows = ranking[ranking["净利润"] < 0].sort_values("净利润").head(5)
        for _, row in loss_rows.iterrows():
            anomalies.append({
                "级别": "关注",
                "项目": row.get("公司", ""),
                "说明": f"本月净亏损 {row['净利润']:,.2f}",
            })
    return anomalies


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
