"""Company filter scope helpers for report pages."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import pandas as pd

from .db_connection import execute_sql


GROUP_SCOPE_CODE = "1"
GROUP_SCOPE_LABEL = "1 - 集团"
CONSOLIDATION_NODE_CODES = {"10101", "10102", "10107", "10108", "10118", "10204"}
ALL_FILTER_VALUES = {"", "不限", "全部", "*", "??"}
MANAGEMENT_FEE_ITEM = "管理费服务费"
INTERNAL_REVENUE_ITEM = "主营业务收入"
REVENUE_TOTAL_ITEMS = {"收入合计", "营业收入", "一、营业收入"}


def is_consolidation_node(company_code: str | None) -> bool:
    code = _clean_code(company_code)
    return code == GROUP_SCOPE_CODE or code in CONSOLIDATION_NODE_CODES


def get_consolidation_company_codes(company_code: str | None) -> list[str]:
    """Return the report scope for a selected company code."""
    code = _clean_code(company_code)
    if not code:
        return []
    if code == GROUP_SCOPE_CODE:
        return _active_company_codes()
    if code in CONSOLIDATION_NODE_CODES:
        return _subtree_codes(code)
    return [code]


def get_report_company_scope(
    company_codes: Sequence[str] | None = None,
    *,
    business_group: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
    default_to_all: bool = True,
) -> list[str]:
    """Resolve selected report companies and apply dimension filters as intersections."""
    selected = _dedupe_codes(company_codes or [])
    if selected:
        base_codes = _dedupe_codes(
            scope_code
            for code in selected
            for scope_code in get_consolidation_company_codes(code)
        )
    elif default_to_all:
        base_codes = _active_company_codes()
    else:
        base_codes = []
    return apply_company_dimension_intersection(
        base_codes,
        business_group=business_group,
        business_type=business_type,
        region=region,
    )


def apply_company_dimension_intersection(
    company_codes: Sequence[str],
    *,
    business_group: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
) -> list[str]:
    codes = _dedupe_codes(company_codes)
    if not codes:
        return []
    filters = {
        "business_group": _clean_filter_value(business_group),
        "business_type": _clean_filter_value(business_type),
        "region": _clean_filter_value(region),
    }
    active_filters = {key: value for key, value in filters.items() if value}

    params: dict[str, Any] = {f"code_{idx}": code for idx, code in enumerate(codes)}
    placeholders = ", ".join(f":code_{idx}" for idx in range(len(codes)))
    conditions = []
    for key, value in active_filters.items():
        params[key] = value
        conditions.append(f"COALESCE(NULLIF(TRIM(d.{key}), ''), '未分组') = :{key}")
    filter_sql = f" AND {' AND '.join(conditions)}" if conditions else ""

    df = execute_sql(
        f"""
        SELECT CAST(c.code AS TEXT) AS code
        FROM companies c
        LEFT JOIN dim_company d
          ON CAST(d.company_id AS TEXT) = CAST(c.code AS TEXT)
        WHERE c.status = 1
          AND c.is_consolidated = 1
          AND CAST(c.code AS TEXT) IN ({placeholders})
          {filter_sql}
        ORDER BY c.tree_path, c.code
        """,
        params,
    )
    allowed = set(df["code"].astype(str).tolist()) if len(df) else set()
    return [code for code in codes if code in allowed]


def get_workspace_company_options(
    *,
    business_group: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
    include_group_scope: bool = True,
) -> pd.DataFrame:
    filters = {
        "business_group": _clean_filter_value(business_group),
        "business_type": _clean_filter_value(business_type),
        "region": _clean_filter_value(region),
    }
    params: dict[str, Any] = {}
    conditions = []
    for key, value in filters.items():
        if value:
            params[key] = value
            conditions.append(f"COALESCE(NULLIF(TRIM(d.{key}), ''), '未分组') = :{key}")
    filter_sql = f" AND {' AND '.join(conditions)}" if conditions else ""

    df = execute_sql(
        f"""
        SELECT
            CAST(c.code AS TEXT) AS code,
            COALESCE(NULLIF(TRIM(c.name), ''), CAST(c.code AS TEXT)) AS name,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS business_group,
            COALESCE(NULLIF(TRIM(d.business_type), ''), '') AS business_type,
            COALESCE(NULLIF(TRIM(d.region), ''), '') AS region
        FROM companies c
        LEFT JOIN dim_company d
          ON CAST(d.company_id AS TEXT) = CAST(c.code AS TEXT)
        WHERE c.status = 1
          AND c.is_consolidated = 1
          {filter_sql}
        ORDER BY c.tree_path, c.code
        """,
        params,
    )
    if include_group_scope and not filters["business_group"] and not filters["business_type"] and not filters["region"]:
        group_row = pd.DataFrame(
            [{"code": GROUP_SCOPE_CODE, "name": "集团", "business_group": "集团合并", "business_type": "", "region": ""}]
        )
        df = pd.concat([group_row, df], ignore_index=True)
    return df


def apply_internal_management_fee_elimination(source_df: pd.DataFrame, company_codes: Sequence[str]) -> pd.DataFrame:
    """Offset subordinate management service fees against parent operating revenue."""
    if source_df is None or source_df.empty or not company_codes:
        return source_df
    df = source_df.copy()
    if "company_code" not in df.columns or "source_item_name" not in df.columns or "current_amount" not in df.columns:
        return df
    if "ytd_amount" in df.columns:
        df["ytd_amount"] = _effective_ytd_amount(df)
    selected_codes = set(_dedupe_codes(company_codes))
    if not any(code in CONSOLIDATION_NODE_CODES or code == GROUP_SCOPE_CODE for code in selected_codes):
        return df

    code_order = _dedupe_codes(df["company_code"].astype(str).tolist())
    parent_map = _nearest_selected_parent_map(code_order, selected_codes)
    if not parent_map:
        return df

    fee_rows = df[df["source_item_name"].astype(str).str.strip() == MANAGEMENT_FEE_ITEM]
    if fee_rows.empty:
        return df
    fee_rows = fee_rows.copy()
    fee_rows["_effective_ytd_amount"] = _effective_ytd_amount(fee_rows)
    for parent_code, child_codes in parent_map.items():
        child_fee_rows = fee_rows.loc[fee_rows["company_code"].astype(str).isin(child_codes)]
        fee_current_amount = float(child_fee_rows["current_amount"].apply(_safe_float).sum())
        fee_ytd_amount = float(child_fee_rows["_effective_ytd_amount"].sum())
        if abs(fee_current_amount) <= 1e-9 and abs(fee_ytd_amount) <= 1e-9:
            continue
        df = _subtract_from_company_items(
            df,
            parent_code,
            {INTERNAL_REVENUE_ITEM} | REVENUE_TOTAL_ITEMS,
            fee_current_amount,
            fee_ytd_amount,
        )
    return df


def _subtract_from_company_items(
    df: pd.DataFrame,
    company_code: str,
    item_names: set[str],
    current_amount: float,
    ytd_amount: float,
) -> pd.DataFrame:
    mask = (df["company_code"].astype(str) == company_code) & df["source_item_name"].astype(str).str.strip().isin(item_names)
    if not mask.any():
        return df
    targets = df.loc[mask].copy()
    codes = targets.get("account_code", pd.Series("", index=targets.index)).astype(str).str.upper()
    priority = pd.Series(2, index=targets.index)
    priority = priority.mask(codes.str.startswith("SUMMARY_"), 1)
    priority = priority.mask(codes.str.startswith("OPERATING_"), 0)
    target_idx = priority.sort_values(kind="mergesort").index[0]
    target_current = _safe_float(df.loc[target_idx, "current_amount"])
    if "ytd_amount" in df.columns:
        target_ytd = _safe_ytd_value(df.loc[target_idx, "ytd_amount"], target_current)
        df.loc[target_idx, "ytd_amount"] = target_ytd - ytd_amount
    df.loc[target_idx, "current_amount"] = target_current - current_amount
    return df


def _effective_ytd_amount(df: pd.DataFrame) -> pd.Series:
    current = df["current_amount"].apply(_safe_float)
    if "ytd_amount" not in df.columns:
        return current
    raw_ytd = df["ytd_amount"]
    missing_ytd = raw_ytd.isna() | raw_ytd.astype(str).str.strip().eq("")
    ytd = raw_ytd.apply(_safe_float)
    ytd.loc[missing_ytd] = current.loc[missing_ytd]
    return ytd


def _safe_ytd_value(value: Any, fallback: float) -> float:
    if pd.isna(value) or str(value).strip() == "":
        return fallback
    return _safe_float(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _nearest_selected_parent_map(company_codes: Sequence[str], selected_codes: set[str]) -> dict[str, list[str]]:
    descendants = _company_ancestor_rows(company_codes)
    parent_map: dict[str, list[str]] = {}
    for code, ancestors in descendants.items():
        for ancestor in ancestors:
            if ancestor in selected_codes and ancestor != code:
                parent_map.setdefault(ancestor, []).append(code)
                break
    return parent_map


def _company_ancestor_rows(company_codes: Sequence[str]) -> dict[str, list[str]]:
    codes = _dedupe_codes(company_codes)
    if not codes:
        return {}
    params = {f"code_{idx}": code for idx, code in enumerate(codes)}
    placeholders = ", ".join(f":code_{idx}" for idx in range(len(codes)))
    df = execute_sql(
        f"""
        SELECT CAST(code AS TEXT) AS code, COALESCE(tree_path, '') AS tree_path
        FROM companies
        WHERE CAST(code AS TEXT) IN ({placeholders})
        """,
        params,
    )
    result: dict[str, list[str]] = {}
    for row in df.to_dict("records"):
        code = str(row.get("code") or "")
        path_codes = [part for part in str(row.get("tree_path") or "").split("/") if part]
        result[code] = list(reversed(path_codes[:-1]))
    return result


def _subtree_codes(company_code: str) -> list[str]:
    code = _clean_code(company_code)
    if not code:
        return []
    df = execute_sql(
        """
        SELECT CAST(child.code AS TEXT) AS code
        FROM companies parent
        JOIN companies child
          ON child.status = 1
         AND child.is_consolidated = 1
         AND (
              child.code = parent.code
              OR child.tree_path = parent.tree_path || '/' || child.code
              OR child.tree_path LIKE parent.tree_path || '/%'
         )
        WHERE parent.code = :code
        ORDER BY child.tree_path, child.code
        """,
        {"code": code},
    )
    return _dedupe_codes(df["code"].astype(str).tolist()) if len(df) else [code]


def _active_company_codes() -> list[str]:
    df = execute_sql(
        """
        SELECT CAST(code AS TEXT) AS code
        FROM companies
        WHERE status = 1
          AND is_consolidated = 1
          AND code <> 'ROOT'
        ORDER BY tree_path, code
        """
    )
    return _dedupe_codes(df["code"].astype(str).tolist()) if len(df) else []


def _dedupe_codes(codes: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_code in codes:
        code = _clean_code(raw_code)
        if code and code not in seen:
            seen.add(code)
            result.append(code)
    return result


def _clean_code(value: str | None) -> str:
    return str(value or "").strip()


def _clean_filter_value(value: str | None) -> str:
    text = str(value or "").strip()
    if text in ALL_FILTER_VALUES or text.replace("?", "") == "":
        return ""
    return text
