"""Operating summary collection rules for management profit tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from .company_hierarchy import get_company_list_for_summary
from .db_connection import execute_sql


@dataclass(frozen=True)
class OperatingSummaryRule:
    summary_item: str
    source_items: tuple[str, ...]
    formula_type: str
    row_type: str
    sort_order: int
    remark: str = ""


OPERATING_SUMMARY_RULES: tuple[OperatingSummaryRule, ...] = (
    OperatingSummaryRule("学生福利及教具", ("学生福利", "教学用具"), "明细加总", "normal", 1),
    OperatingSummaryRule("房租水电", ("房租", "水电费"), "明细加总", "normal", 2),
    OperatingSummaryRule(
        "人工",
        ("工资", "奖金", "社保", "社保费", "公积金", "福利费", "教师福利"),
        "明细加总",
        "normal",
        3,
        "工资、奖金、社保、公积金、福利",
    ),
    OperatingSummaryRule("税金", ("发票税", "税金及附加"), "明细加总", "normal", 4),
    OperatingSummaryRule("销售费用", ("业务宣传费",), "明细加总", "normal", 5),
    OperatingSummaryRule(
        "办公",
        ("办公费", "维修费", "通信费", "通讯费", "快递费"),
        "明细加总",
        "normal",
        6,
        "办公、维修、通讯、快递",
    ),
    OperatingSummaryRule("交际费", ("招待费",), "明细加总", "normal", 7),
    OperatingSummaryRule("折旧及摊销", ("折旧费", "待摊费"), "明细加总", "normal", 8),
    OperatingSummaryRule("管理中心", ("管理费服务费",), "明细加总", "normal", 9),
    OperatingSummaryRule("财务费用", ("财务费用",), "明细加总", "normal", 10),
    OperatingSummaryRule("其他", (), "剩余法", "normal", 11),
    OperatingSummaryRule("成本费用合计", (), "指标公式", "summary", 12, "来自收入成本费用明细表"),
    OperatingSummaryRule("收入合计", (), "指标公式", "summary", 13, "来自收入成本费用明细表"),
    OperatingSummaryRule("净利润", (), "指标公式", "profit", 14, "收入合计 - 成本费用合计"),
    OperatingSummaryRule("实际成本", (), "指标公式", "summary", 15, "成本费用合计 - 折旧及摊销"),
    OperatingSummaryRule("净利润（不含折旧与摊销）", (), "指标公式", "profit", 16, "净利润 + 折旧及摊销"),
)

SUMMARY_ITEM_ORDER = [rule.summary_item for rule in OPERATING_SUMMARY_RULES]
NORMAL_SUMMARY_ITEMS = [rule.summary_item for rule in OPERATING_SUMMARY_RULES if rule.row_type == "normal"]
EXPLICIT_NORMAL_ITEMS = [rule.summary_item for rule in OPERATING_SUMMARY_RULES if rule.row_type == "normal" and rule.formula_type == "明细加总"]

REVENUE_TOTAL_NAMES = {"收入合计", "营业收入", "一、营业收入"}
COST_TOTAL_NAMES = {"成本费用合计", "成本费用", "成本费用合计数"}
DEPRECIATION_TOTAL_NAMES = {"折旧及摊销", "折旧与摊销", "折旧与待摊费用合计", "折旧及待摊费用合计"}
NET_PROFIT_TOTAL_NAMES = {"净利润"}
ACTUAL_COST_TOTAL_NAMES = {"实际成本"}
NET_PROFIT_EXCLUDING_DEPRECIATION_NAMES = {
    "净利润（不含折旧与摊销）",
    "净利润（不含计提折旧与摊销）",
}


def get_operating_summary_source_detail(
    period: str,
    company_codes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Read source detail rows from the income/cost/expense detail table."""
    params: dict[str, Any] = {"period": period}
    company_sql = ""
    if company_codes is not None:
        codes = _expand_company_codes(company_codes)
        if not codes:
            return pd.DataFrame()
        holders = []
        for idx, code in enumerate(codes):
            key = f"company_{idx}"
            params[key] = code
            holders.append(f":{key}")
        company_sql = f" AND d.company_code IN ({', '.join(holders)})"

    return execute_sql(
        f"""
        SELECT
            d.company_code,
            COALESCE(c.short_name, c.name, d.company_code) AS company_name,
            d.period,
            d.item_name AS source_item_name,
            COALESCE(d.dept_name, d.category, '') AS source_section,
            d.amount AS current_amount,
            d.ytd_amount AS ytd_amount,
            d.item_code AS account_code,
            d.item_name AS account_name,
            d.import_batch
        FROM pl_detail d
        LEFT JOIN companies c ON d.company_code = c.code
        WHERE d.period = :period
          {company_sql}
        ORDER BY d.company_code, d.category, d.item_code, d.item_name
        """,
        params,
    )


def _expand_company_codes(company_codes: Sequence[str]) -> list[str]:
    """Expand selected company nodes to their organization-tree descendants."""
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_code in company_codes:
        code = str(raw_code or "").strip()
        if not code:
            continue
        try:
            descendants = get_company_list_for_summary(code)
        except Exception:
            descendants = [code]
        for descendant in descendants or [code]:
            descendant_code = str(descendant or "").strip()
            if descendant_code and descendant_code not in seen:
                seen.add(descendant_code)
                expanded.append(descendant_code)
    return expanded


def get_operating_summary_periods() -> list[str]:
    """Return periods that exist in the income/cost/expense detail table."""
    try:
        df = execute_sql(
            """
            SELECT DISTINCT period
            FROM pl_detail
            WHERE period IS NOT NULL
            ORDER BY period DESC
            """
        )
    except Exception:
        return []
    return df["period"].dropna().astype(str).tolist() if len(df) else []


def build_operating_summary_rows(
    source_df: pd.DataFrame,
    previous_source_df: pd.DataFrame | None = None,
    max_company_cols: int = 4,
) -> list[dict[str, Any]]:
    """Build operating summary rows from source detail and collection rules."""
    source_df = _normalize_source_df(source_df)
    previous_source_df = _normalize_source_df(previous_source_df)
    if source_df.empty:
        return []

    company_names = _ordered_company_names(source_df)[:max_company_cols]
    current = _collect_period_values(source_df, company_names)
    previous = _collect_period_values(previous_source_df, company_names) if not previous_source_df.empty else {}
    cost_total = _safe_float(current.get("成本费用合计", {}).get("total"))
    revenue_total = _safe_float(current.get("收入合计", {}).get("total"))
    ytd_cost_total = _safe_float(current.get("成本费用合计", {}).get("ytd_total", cost_total))
    ytd_revenue_total = _safe_float(current.get("收入合计", {}).get("ytd_total", revenue_total))

    rows: list[dict[str, Any]] = []
    for rule in OPERATING_SUMMARY_RULES:
        item = rule.summary_item
        current_item = current.get(item, {"total": 0.0, "companies": {}, "source_items": []})
        previous_item = previous.get(item, {})
        amount = _safe_float(current_item.get("total"))
        previous_amount = previous_item.get("total")
        has_previous = previous_amount is not None
        previous_float = _safe_float(previous_amount)
        mom = (
            _safe_ratio(amount - previous_float, abs(previous_float))
            if has_previous and abs(previous_float) > 1e-9
            else None
        )
        rows.append(
            {
                "row_idx": len(rows),
                "费用科目": item,
                "合计": amount,
                "2026合计": _safe_float(current_item.get("ytd_total", amount)),
                "占费用比": _safe_ratio(amount, cost_total) if rule.row_type == "normal" or item in {"成本费用合计", "实际成本"} else None,
                "占收入比": _safe_ratio(amount, revenue_total),
                "年度占费用比": (
                    _safe_ratio(current_item.get("ytd_total", amount), ytd_cost_total)
                    if rule.row_type == "normal" or item in {"成本费用合计", "实际成本"}
                    else None
                ),
                "年度占收入比": _safe_ratio(current_item.get("ytd_total", amount), ytd_revenue_total),
                "上月": previous_float if has_previous else None,
                "环比": mom,
                "备注": rule.remark or _default_remark(item, mom),
                "companies": current_item.get("companies", {}),
                "ytd_companies": current_item.get("ytd_companies", {}),
                "previous_companies": previous_item.get("companies", {}),
                "row_type": rule.row_type,
                "formula_type": rule.formula_type,
                "source_items": current_item.get("source_items", []),
                "is_profit": rule.row_type == "profit",
                "is_total": rule.row_type == "summary",
            }
        )
    return rows


def build_empty_operating_summary_rows() -> list[dict[str, Any]]:
    """Return the operating summary structure when source detail is not imported yet."""
    rows: list[dict[str, Any]] = []
    for rule in OPERATING_SUMMARY_RULES:
        rows.append(
            {
                "row_idx": len(rows),
                "费用科目": rule.summary_item,
                "合计": 0.0,
                "2026合计": 0.0,
                "占费用比": None,
                "占收入比": None,
                "上月": None,
                "环比": None,
                "备注": rule.remark or "等待导入收入成本费用明细表",
                "companies": {},
                "previous_companies": {},
                "row_type": rule.row_type,
                "formula_type": rule.formula_type,
                "source_items": list(rule.source_items),
                "is_profit": rule.row_type == "profit",
                "is_total": rule.row_type == "summary",
            }
        )
    return rows


def _normalize_source_df(source_df: pd.DataFrame | None) -> pd.DataFrame:
    if source_df is None or len(source_df) == 0:
        return pd.DataFrame()
    df = source_df.copy()
    rename_map = {
        "item_name": "source_item_name",
        "amount": "current_amount",
        "category": "source_section",
    }
    df = df.rename(columns={old: new for old, new in rename_map.items() if old in df.columns and new not in df.columns})
    required_defaults = {
        "company_name": "",
        "source_item_name": "",
        "source_section": "",
        "current_amount": 0.0,
        "account_code": "",
    }
    for column, default in required_defaults.items():
        if column not in df.columns:
            df[column] = default
    df["company_name"] = df["company_name"].astype(str).replace("", "未指定主体")
    df["source_item_name"] = df["source_item_name"].astype(str).str.strip()
    df["current_amount"] = df["current_amount"].apply(_safe_float)
    if "ytd_amount" not in df.columns:
        df["ytd_amount"] = df["current_amount"]
    else:
        raw_ytd = df["ytd_amount"]
        missing_ytd = raw_ytd.isna() | raw_ytd.astype(str).str.strip().eq("")
        df["ytd_amount"] = df["ytd_amount"].apply(_safe_float)
        df.loc[missing_ytd, "ytd_amount"] = df.loc[missing_ytd, "current_amount"]
    return df


def _ordered_company_names(source_df: pd.DataFrame) -> list[str]:
    return source_df["company_name"].dropna().astype(str).drop_duplicates().tolist()


def _collect_period_values(source_df: pd.DataFrame, company_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for rule in OPERATING_SUMMARY_RULES:
        if rule.formula_type != "明细加总":
            continue
        fallback = _sum_source_items(source_df, rule.source_items, company_names)
        values[rule.summary_item] = _preferred_period_value(
            source_df,
            _preferred_names_for_item(rule.summary_item),
            company_names,
            fallback,
            canonical_item=rule.summary_item,
        )

    explicit_total = sum(_safe_float(values.get(item, {}).get("total")) for item in EXPLICIT_NORMAL_ITEMS)
    explicit_ytd_total = sum(_safe_float(values.get(item, {}).get("ytd_total")) for item in EXPLICIT_NORMAL_ITEMS)
    explicit_company_total = {
        company: sum(_safe_float(values.get(item, {}).get("companies", {}).get(company)) for item in EXPLICIT_NORMAL_ITEMS)
        for company in company_names
    }
    explicit_ytd_company_total = {
        company: sum(_safe_float(values.get(item, {}).get("ytd_companies", {}).get(company)) for item in EXPLICIT_NORMAL_ITEMS)
        for company in company_names
    }

    cost_fallback = {
        "total": explicit_total,
        "ytd_total": explicit_ytd_total,
        "companies": explicit_company_total,
        "ytd_companies": explicit_ytd_company_total,
        "source_items": ["明细归集合计"],
    }
    revenue_fallback = {
        "total": 0.0,
        "ytd_total": 0.0,
        "companies": {company: 0.0 for company in company_names},
        "ytd_companies": {company: 0.0 for company in company_names},
        "source_items": [],
    }
    cost_value = _preferred_period_value(
        source_df,
        COST_TOTAL_NAMES,
        company_names,
        cost_fallback,
        canonical_item="成本费用合计",
    )
    revenue_value = _preferred_period_value(
        source_df,
        REVENUE_TOTAL_NAMES,
        company_names,
        revenue_fallback,
        canonical_item="收入合计",
    )
    cost_total = _safe_float(cost_value.get("total"))
    cost_ytd_total = _safe_float(cost_value.get("ytd_total", cost_total))
    revenue_total = _safe_float(revenue_value.get("total"))
    revenue_ytd_total = _safe_float(revenue_value.get("ytd_total", revenue_total))
    cost_companies = {company: _safe_float(cost_value.get("companies", {}).get(company)) for company in company_names}
    cost_ytd_companies = {
        company: _safe_float(cost_value.get("ytd_companies", {}).get(company))
        for company in company_names
    }
    other_fallback_companies = {
        company: cost_companies.get(company, 0.0) - explicit_company_total.get(company, 0.0)
        for company in company_names
    }
    other_ytd_fallback_companies = {
        company: cost_ytd_companies.get(company, 0.0) - explicit_ytd_company_total.get(company, 0.0)
        for company in company_names
    }
    other_total = cost_total - explicit_total
    other_ytd_total = cost_ytd_total - explicit_ytd_total
    other_fallback = {
        "total": other_total,
        "ytd_total": other_ytd_total,
        "companies": other_fallback_companies,
        "ytd_companies": other_ytd_fallback_companies,
        "source_items": ["成本费用合计中未被明确归集的明细项目"],
    }
    values["其他"] = {
        **_preferred_period_value(source_df, {"其他"}, company_names, other_fallback, canonical_item="其他"),
    }
    depreciation = _safe_float(values.get("折旧及摊销", {}).get("total"))
    depreciation_ytd = _safe_float(values.get("折旧及摊销", {}).get("ytd_total", depreciation))
    values["成本费用合计"] = {**cost_value, "source_items": cost_value.get("source_items") or ["成本费用合计"]}
    values["收入合计"] = {**revenue_value, "source_items": revenue_value.get("source_items") or ["收入合计"]}
    net_profit_fallback = {
        "total": revenue_total - cost_total,
        "ytd_total": revenue_ytd_total - cost_ytd_total,
        "companies": _binary_company_formula(values, "收入合计", "成本费用合计", company_names),
        "ytd_companies": _binary_company_formula(values, "收入合计", "成本费用合计", company_names, ytd=True),
        "source_items": ["收入合计", "成本费用合计"],
    }
    values["净利润"] = _preferred_period_value(
        source_df,
        NET_PROFIT_TOTAL_NAMES,
        company_names,
        net_profit_fallback,
        canonical_item="净利润",
    )
    actual_cost_fallback = {
        "total": cost_total - depreciation,
        "ytd_total": cost_ytd_total - depreciation_ytd,
        "companies": _binary_company_formula(values, "成本费用合计", "折旧及摊销", company_names),
        "ytd_companies": _binary_company_formula(values, "成本费用合计", "折旧及摊销", company_names, ytd=True),
        "source_items": ["成本费用合计", "折旧及摊销"],
    }
    values["实际成本"] = _preferred_period_value(
        source_df,
        ACTUAL_COST_TOTAL_NAMES,
        company_names,
        actual_cost_fallback,
        canonical_item="实际成本",
    )
    net_profit_excluding_depreciation_fallback = {
        "total": _safe_float(values.get("净利润", {}).get("total")) + depreciation,
        "ytd_total": _safe_float(values.get("净利润", {}).get("ytd_total")) + depreciation_ytd,
        "companies": _company_add(values, "净利润", "折旧及摊销", company_names),
        "ytd_companies": _company_add(values, "净利润", "折旧及摊销", company_names, ytd=True),
        "source_items": ["净利润", "折旧及摊销"],
    }
    values["净利润（不含折旧与摊销）"] = _preferred_period_value(
        source_df,
        NET_PROFIT_EXCLUDING_DEPRECIATION_NAMES,
        company_names,
        net_profit_excluding_depreciation_fallback,
        canonical_item="净利润（不含折旧与摊销）",
    )
    return values


def _sum_source_items(source_df: pd.DataFrame, source_items: Sequence[str], company_names: Sequence[str]) -> dict[str, Any]:
    names = {str(item).strip() for item in source_items}
    detail_df = _detail_source_rows(source_df)
    matched = detail_df[detail_df["source_item_name"].isin(names)]
    total = float(matched["current_amount"].sum()) if len(matched) else 0.0
    ytd_total = float(matched["ytd_amount"].sum()) if len(matched) else 0.0
    companies = {
        company: float(matched.loc[matched["company_name"] == company, "current_amount"].sum()) if len(matched) else 0.0
        for company in company_names
    }
    ytd_companies = {
        company: float(matched.loc[matched["company_name"] == company, "ytd_amount"].sum()) if len(matched) else 0.0
        for company in company_names
    }
    return {
        "total": total,
        "ytd_total": ytd_total,
        "companies": companies,
        "ytd_companies": ytd_companies,
        "source_items": sorted(set(matched["source_item_name"].astype(str).tolist())),
    }


def _preferred_names_for_item(summary_item: str) -> set[str]:
    if summary_item == "折旧及摊销":
        return DEPRECIATION_TOTAL_NAMES
    return {summary_item}


def _preferred_period_value(
    source_df: pd.DataFrame,
    names: set[str],
    company_names: Sequence[str],
    fallback: dict[str, Any],
    canonical_item: str | None = None,
) -> dict[str, Any]:
    matched = _preferred_source_rows(source_df, names, canonical_item)
    fallback_companies = fallback.get("companies", {})
    fallback_ytd_companies = fallback.get("ytd_companies", fallback_companies)
    companies: dict[str, float] = {}
    ytd_companies: dict[str, float] = {}
    used_source_items: set[str] = set()
    for company in company_names:
        company_rows = matched.loc[matched["company_name"] == company] if len(matched) else matched
        if len(company_rows):
            companies[company] = float(company_rows["current_amount"].sum())
            ytd_companies[company] = float(company_rows["ytd_amount"].sum())
            used_source_items.update(company_rows["source_item_name"].astype(str).tolist())
        else:
            companies[company] = _safe_float(fallback_companies.get(company))
            ytd_companies[company] = _safe_float(fallback_ytd_companies.get(company))
    total = sum(companies.values()) if company_names else _safe_float(fallback.get("total"))
    ytd_total = sum(ytd_companies.values()) if company_names else _safe_float(fallback.get("ytd_total", fallback.get("total")))
    return {
        "total": total,
        "ytd_total": ytd_total,
        "companies": companies,
        "ytd_companies": ytd_companies,
        "source_items": sorted(used_source_items) if used_source_items else list(fallback.get("source_items", [])),
    }


def _preferred_source_rows(source_df: pd.DataFrame, names: set[str], canonical_item: str | None = None) -> pd.DataFrame:
    matched = source_df[source_df["source_item_name"].isin(names)].copy()
    if matched.empty:
        return matched
    matched["_source_priority"] = _source_priority(matched)
    company_key = "company_code" if "company_code" in matched.columns else "company_name"
    best_priority = matched.groupby(company_key)["_source_priority"].transform("min")
    matched = matched.loc[matched["_source_priority"] == best_priority].copy()
    matched["_source_order"] = _source_order(matched)
    matched["_canonical_item"] = canonical_item or matched["source_item_name"]
    matched = matched.sort_values("_source_order", kind="mergesort").drop_duplicates(
        subset=[company_key, "_canonical_item"],
        keep="last",
    )
    return matched.drop(columns=["_source_priority", "_source_order", "_canonical_item"])


def _source_priority(source_df: pd.DataFrame) -> pd.Series:
    codes = source_df.get("account_code", pd.Series("", index=source_df.index)).astype(str).str.strip().str.upper()
    priority = pd.Series(2, index=source_df.index)
    priority = priority.mask(codes.str.startswith("SUMMARY_"), 1)
    priority = priority.mask(codes.str.startswith("OPERATING_"), 0)
    return priority


def _source_order(source_df: pd.DataFrame) -> pd.Series:
    for column in ("source_row", "row_id", "id"):
        if column in source_df.columns:
            order = pd.to_numeric(source_df[column], errors="coerce")
            if order.notna().any():
                return order.fillna(pd.Series(range(len(source_df)), index=source_df.index))
    return pd.Series(range(len(source_df)), index=source_df.index)


def _detail_source_rows(source_df: pd.DataFrame) -> pd.DataFrame:
    codes = source_df.get("account_code", pd.Series("", index=source_df.index)).astype(str).str.strip().str.upper()
    return source_df.loc[~codes.str.startswith("OPERATING_") & ~codes.str.startswith("SUMMARY_")]


def _binary_company_formula(
    values: dict[str, dict[str, Any]],
    left: str,
    right: str,
    company_names: Sequence[str],
    *,
    ytd: bool = False,
) -> dict[str, float]:
    company_key = "ytd_companies" if ytd else "companies"
    return {
        company: _safe_float(values.get(left, {}).get(company_key, {}).get(company)) - _safe_float(values.get(right, {}).get(company_key, {}).get(company))
        for company in company_names
    }


def _company_add(
    values: dict[str, dict[str, Any]],
    left: str,
    right: str,
    company_names: Sequence[str],
    *,
    ytd: bool = False,
) -> dict[str, float]:
    company_key = "ytd_companies" if ytd else "companies"
    return {
        company: _safe_float(values.get(left, {}).get(company_key, {}).get(company)) + _safe_float(values.get(right, {}).get(company_key, {}).get(company))
        for company in company_names
    }


def _default_remark(item_name: str, mom: float | None) -> str:
    if mom is not None and abs(_safe_float(mom)) >= 0.3:
        return "异常需备注"
    return ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    denominator = _safe_float(denominator)
    if abs(denominator) < 1e-9:
        return None
    return _safe_float(numerator) / denominator
