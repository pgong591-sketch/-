"""Base-settings service layer.

This module is the shared entry point for company master data, dimension
attributes, alias resolution, hierarchy scope, and base-setting health checks.
It intentionally does not write aliases from fuzzy matches.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy import text

from .company_dimension import (
    BUSINESS_GROUP_OPTIONS,
    normalize_business_group as _normalize_business_group,
    seed_dim_company_from_companies,
)
from .company_hierarchy import get_company_list_for_summary
from .db_connection import execute_sql, get_session, table_exists
from .operating_summary import SUMMARY_ITEM_ORDER


ALL_COMPANIES_VALUE = ""
BASE_OPERATING_ITEM_ALIASES = {"差旅交际费": "交际费"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _active_company_where(include_inactive: bool = False) -> str:
    return "1=1" if include_inactive else "COALESCE(c.status, 1) = 1"


def get_company_options(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Return company options with base dimension attributes."""
    seed_dim_company_from_companies()
    rows = execute_sql(
        f"""
        SELECT
            CAST(c.code AS TEXT) AS company_code,
            COALESCE(NULLIF(TRIM(c.name), ''), CAST(c.code AS TEXT)) AS company_name,
            COALESCE(NULLIF(TRIM(c.short_name), ''), '') AS short_name,
            COALESCE(NULLIF(TRIM(c.parent_code), ''), '') AS parent_code,
            COALESCE(c.level, 0) AS level,
            COALESCE(c.tree_path, '') AS tree_path,
            COALESCE(c.is_consolidated, 1) AS is_consolidated,
            COALESCE(c.status, 1) AS status,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '') AS business_group,
            COALESCE(NULLIF(TRIM(d.business_type), ''), '') AS business_type,
            COALESCE(NULLIF(TRIM(d.region), ''), '') AS region,
            COALESCE(d.is_operational, 1) AS is_operational
        FROM companies c
        LEFT JOIN dim_company d ON d.company_id = c.code
        WHERE {_active_company_where(include_inactive)}
        ORDER BY c.tree_path, c.code
        """
    )
    if rows.empty:
        return []
    options: list[dict[str, Any]] = []
    for row in rows.to_dict("records"):
        code = _clean(row.get("company_code"))
        name = _clean(row.get("company_name")) or code
        group = normalize_business_group(row.get("business_group"))
        label = f"{code} - {name}" + (f" / {group}" if group else "")
        item = dict(row)
        item["company_code"] = code
        item["company_name"] = name
        item["business_group"] = group
        item["label"] = label
        item["value"] = code
        options.append(item)
    return options


def get_company_scope_codes(
    company_code: str | None,
    include_descendants: bool = True,
    include_inactive: bool = False,
    consolidated_only: bool = True,
) -> list[str]:
    """Return company codes for a company scope, optionally including descendants."""
    clean_code = _clean(company_code)
    if not clean_code:
        conditions = [_active_company_where(include_inactive)]
        if consolidated_only:
            conditions.append("COALESCE(c.is_consolidated, 1) = 1")
        rows = execute_sql(
            f"""
            SELECT CAST(c.code AS TEXT) AS code
            FROM companies c
            WHERE {' AND '.join(conditions)}
            ORDER BY c.tree_path, c.code
            """
        )
        return rows["code"].astype(str).tolist() if len(rows) else []

    if include_descendants:
        codes = [str(code) for code in get_company_list_for_summary(clean_code) if str(code)]
    else:
        codes = [clean_code]
    if not codes:
        return []

    params = {f"code_{idx}": code for idx, code in enumerate(codes)}
    placeholders = ", ".join(f":code_{idx}" for idx in range(len(codes)))
    conditions = [f"c.code IN ({placeholders})", _active_company_where(include_inactive)]
    if consolidated_only:
        conditions.append("COALESCE(c.is_consolidated, 1) = 1")
    rows = execute_sql(
        f"""
        SELECT CAST(c.code AS TEXT) AS code
        FROM companies c
        WHERE {' AND '.join(conditions)}
        ORDER BY c.tree_path, c.code
        """,
        params,
    )
    return rows["code"].astype(str).tolist() if len(rows) else []


def _company_identity_rows() -> list[dict[str, str]]:
    rows = execute_sql(
        """
        SELECT CAST(code AS TEXT) AS label, CAST(code AS TEXT) AS company_code,
               COALESCE(name, code) AS company_name, 'code' AS source
        FROM companies
        WHERE COALESCE(status, 1) = 1
        UNION ALL
        SELECT name AS label, CAST(code AS TEXT) AS company_code,
               COALESCE(name, code) AS company_name, 'name' AS source
        FROM companies
        WHERE COALESCE(status, 1) = 1 AND name IS NOT NULL AND TRIM(name) != ''
        UNION ALL
        SELECT short_name AS label, CAST(code AS TEXT) AS company_code,
               COALESCE(name, code) AS company_name, 'short_name' AS source
        FROM companies
        WHERE COALESCE(status, 1) = 1 AND short_name IS NOT NULL AND TRIM(short_name) != ''
        UNION ALL
        SELECT alias AS label, CAST(a.company_code AS TEXT) AS company_code,
               COALESCE(c.name, a.company_code) AS company_name, 'alias' AS source
        FROM company_aliases a
        LEFT JOIN companies c ON c.code = a.company_code
        WHERE COALESCE(a.status, 1) = 1
        """
    )
    if rows.empty:
        return []
    return [
        {
            "label": _clean(row.get("label")),
            "company_code": _clean(row.get("company_code")),
            "company_name": _clean(row.get("company_name")),
            "source": _clean(row.get("source")),
        }
        for row in rows.to_dict("records")
        if _clean(row.get("label")) and _clean(row.get("company_code"))
    ]


def _distinct_suggestions(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    suggestions: dict[str, dict[str, str]] = {}
    for item in matches:
        code = item["company_code"]
        suggestions.setdefault(
            code,
            {
                "company_code": code,
                "company_name": item.get("company_name") or code,
                "match_source": item.get("source", ""),
            },
        )
    return [suggestions[code] for code in sorted(suggestions)]


def resolve_company_identity(raw_name: str, mode: str = "strict") -> dict[str, Any]:
    """Resolve raw company text without creating aliases from fuzzy matches."""
    value = _clean(raw_name)
    result = {
        "ok": False,
        "company_code": "",
        "company_name": "",
        "match_type": "none",
        "suggestions": [],
    }
    if not value:
        return result

    rows = _company_identity_rows()
    exact = [
        item for item in rows
        if item["label"] == value or item["company_code"] == value
    ]
    exact_suggestions = _distinct_suggestions(exact)
    if len(exact_suggestions) == 1:
        match = exact_suggestions[0]
        return {
            "ok": True,
            "company_code": match["company_code"],
            "company_name": match["company_name"],
            "match_type": match["match_source"] or "exact",
            "suggestions": [],
        }
    if len(exact_suggestions) > 1:
        result["match_type"] = "ambiguous_exact"
        result["suggestions"] = exact_suggestions
        return result

    fuzzy = [
        item for item in rows
        if item["label"] and (value in item["label"] or item["label"] in value)
    ]
    fuzzy_suggestions = _distinct_suggestions(fuzzy)
    if mode == "strict":
        result["match_type"] = "strict_no_exact"
        return result
    result["match_type"] = "fuzzy_suggestions" if fuzzy_suggestions else "none"
    result["suggestions"] = fuzzy_suggestions
    return result


def get_company_dimension(company_code: str) -> dict[str, Any] | None:
    """Return one company's dimension row."""
    code = _clean(company_code)
    if not code:
        return None
    seed_dim_company_from_companies()
    df = execute_sql(
        """
        SELECT
            CAST(c.code AS TEXT) AS company_code,
            COALESCE(c.name, c.code) AS company_name,
            COALESCE(c.parent_code, '') AS parent_code,
            COALESCE(c.level, 0) AS level,
            COALESCE(d.business_group, '') AS business_group,
            COALESCE(d.business_type, '') AS business_type,
            COALESCE(d.region, '') AS region,
            COALESCE(d.is_operational, 1) AS is_operational
        FROM companies c
        LEFT JOIN dim_company d ON d.company_id = c.code
        WHERE c.code = :code
        """,
        {"code": code},
    )
    if df.empty:
        return None
    item = df.iloc[0].to_dict()
    item["business_group"] = normalize_business_group(item.get("business_group"))
    return item


def get_business_group_options() -> list[str]:
    """Return formal business-group options from the existing dimension module."""
    return [item for item in BUSINESS_GROUP_OPTIONS if _clean(item)]


def normalize_business_group(value: Any) -> str:
    """Normalize historical business-group labels to the current formal labels."""
    return _normalize_business_group(value)


def normalize_operating_item(value: Any) -> str:
    """Normalize operating-summary item aliases without changing rules."""
    item = _clean(value)
    normalized = BASE_OPERATING_ITEM_ALIASES.get(item, item)
    return normalized if normalized in SUMMARY_ITEM_ORDER else normalized


def _count_sql(sql: str, params: dict[str, Any] | None = None) -> int:
    try:
        df = execute_sql(sql, params)
        if df.empty:
            return 0
        return int(df.iloc[0, 0] or 0)
    except Exception:
        return 0


def _optional_count_sql(sql: str, params: dict[str, Any] | None = None) -> int | None:
    try:
        df = execute_sql(sql, params)
        if df.empty:
            return 0
        return int(df.iloc[0, 0] or 0)
    except Exception:
        return None


def _table_columns(table_name: str) -> set[str]:
    try:
        columns_df = execute_sql(f"PRAGMA table_info({table_name})")
    except Exception:
        return set()
    if columns_df.empty or "name" not in columns_df:
        return set()
    return {str(row["name"]) for _, row in columns_df.iterrows()}


def _unresolved_company_issue_count() -> int | None:
    if not table_exists("import_issue_pool"):
        return None
    columns = _table_columns("import_issue_pool")
    if not {"issue_type", "issue_message"}.issubset(columns):
        return None
    return _optional_count_sql(
        """
        SELECT COUNT(*)
        FROM import_issue_pool
        WHERE LOWER(COALESCE(issue_type, '')) IN (
            'company', 'company_name', 'unresolved_company',
            'unrecognized_company', 'missing_company'
        )
           OR COALESCE(issue_message, '') LIKE '%公司%'
        """
    )


def _tree_path_issue_count() -> int:
    missing_or_parent_issue = _count_sql(
        """
        SELECT COUNT(*)
        FROM companies c
        LEFT JOIN companies p ON p.code = c.parent_code
        WHERE COALESCE(c.status, 1) = 1
          AND (
            c.tree_path IS NULL
            OR TRIM(c.tree_path) = ''
            OR (
                c.parent_code IS NOT NULL
                AND TRIM(c.parent_code) != ''
                AND p.code IS NULL
            )
            OR (
                c.parent_code IS NOT NULL
                AND TRIM(c.parent_code) != ''
                AND INSTR(COALESCE(c.tree_path, ''), c.parent_code) = 0
            )
          )
        """
    )
    duplicate_paths = _count_sql(
        """
        SELECT COUNT(*)
        FROM (
            SELECT tree_path
            FROM companies
            WHERE COALESCE(status, 1) = 1
              AND tree_path IS NOT NULL
              AND TRIM(tree_path) != ''
            GROUP BY tree_path
            HAVING COUNT(*) > 1
        )
        """
    )
    return missing_or_parent_issue + duplicate_paths


def get_base_settings_overview() -> dict[str, Any]:
    """Return base-settings summary counts."""
    missing_dimension_count = _count_sql(
        """
        SELECT COUNT(*)
        FROM companies c
        LEFT JOIN dim_company d ON d.company_id = c.code
        WHERE COALESCE(c.status, 1) = 1 AND d.company_id IS NULL
        """
    )
    return {
        "company_count": _count_sql("SELECT COUNT(*) FROM companies WHERE COALESCE(status, 1) = 1"),
        "inactive_company_count": _count_sql("SELECT COUNT(*) FROM companies WHERE COALESCE(status, 1) = 0"),
        "alias_count": _count_sql("SELECT COUNT(*) FROM company_aliases WHERE COALESCE(status, 1) = 1"),
        "dimension_count": _count_sql("SELECT COUNT(*) FROM dim_company"),
        "ownership_count": _count_sql("SELECT COUNT(*) FROM ownership"),
        "ungrouped_company_count": _count_sql(
            """
            SELECT COUNT(*)
            FROM dim_company d
            JOIN companies c ON c.code = d.company_id
            WHERE COALESCE(c.status, 1) = 1
              AND (
                d.business_group IS NULL
                OR TRIM(d.business_group) = ''
                OR TRIM(d.business_group) = '未分组'
              )
            """
        ),
        "alias_conflict_count": _count_sql(
            """
            SELECT COUNT(*)
            FROM (
                SELECT alias
                FROM company_aliases
                WHERE COALESCE(status, 1) = 1
                  AND alias IS NOT NULL
                  AND TRIM(alias) != ''
                GROUP BY alias
                HAVING COUNT(DISTINCT company_code) > 1
            )
            """
        ),
        "unresolved_company_name_count": _unresolved_company_issue_count(),
        "missing_dimension_count": missing_dimension_count,
        "tree_path_issue_count": _tree_path_issue_count(),
        "business_group_count": _count_sql(
            "SELECT COUNT(DISTINCT NULLIF(TRIM(business_group), '')) FROM dim_company"
        ),
        "import_issue_count": (
            _count_sql("SELECT COUNT(*) FROM import_issue_pool")
            if table_exists("import_issue_pool")
            else 0
        ),
        "import_issue_pool_available": table_exists("import_issue_pool"),
        "change_log_available": table_exists("base_settings_change_log"),
    }


def get_base_health_checks() -> list[dict[str, Any]]:
    """Return data-governance health checks for base settings."""
    checks = [
        {
            "check_key": "companies_without_dimension",
            "label": "公司缺少维度属性",
            "severity": "warning",
            "count": _count_sql(
                """
                SELECT COUNT(*)
                FROM companies c
                LEFT JOIN dim_company d ON d.company_id = c.code
                WHERE COALESCE(c.status, 1) = 1 AND d.company_id IS NULL
                """
            ),
        },
        {
            "check_key": "dimension_orphans",
            "label": "维度属性引用不存在公司",
            "severity": "error",
            "count": _count_sql(
                """
                SELECT COUNT(*)
                FROM dim_company d
                LEFT JOIN companies c ON c.code = d.company_id
                WHERE c.code IS NULL
                """
            ),
        },
        {
            "check_key": "ownership_orphans",
            "label": "股权关系引用不存在公司",
            "severity": "error",
            "count": _count_sql(
                """
                SELECT COUNT(*)
                FROM ownership o
                LEFT JOIN companies p ON p.code = o.parent_code
                LEFT JOIN companies s ON s.code = o.sub_code
                WHERE p.code IS NULL OR s.code IS NULL
                """
            ),
        },
        {
            "check_key": "companies_without_tree_path",
            "label": "公司缺少组织树路径",
            "severity": "warning",
            "count": _count_sql(
                """
                SELECT COUNT(*)
                FROM companies
                WHERE COALESCE(status, 1) = 1
                  AND (tree_path IS NULL OR TRIM(tree_path) = '')
                """
            ),
        },
        {
            "check_key": "aliases_to_missing_company",
            "label": "别名引用不存在公司",
            "severity": "error",
            "count": _count_sql(
                """
                SELECT COUNT(*)
                FROM company_aliases a
                LEFT JOIN companies c ON c.code = a.company_code
                WHERE c.code IS NULL
                """
            ),
        },
    ]
    for item in checks:
        item["status"] = "ok" if item["count"] == 0 else "issue"
    return checks


def record_import_issue(
    *,
    batch_no: str = "",
    file_name: str = "",
    company_code: str = "",
    period: str = "",
    report_type: str = "",
    issue_type: str = "",
    issue_message: str = "",
    severity: str = "warning",
    source: str = "precheck",
    status: str = "open",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an import issue when `import_issue_pool` exists.

    This function does not create the table, so adding the service layer does
    not mutate database structure.
    """
    if not table_exists("import_issue_pool"):
        return {"recorded": False, "reason": "missing_import_issue_pool"}

    values = {
        "batch_no": _clean(batch_no),
        "file_name": _clean(file_name),
        "company_code": _clean(company_code),
        "period": _clean(period),
        "report_type": _clean(report_type),
        "issue_type": _clean(issue_type),
        "issue_message": _clean(issue_message),
        "severity": _clean(severity) or "warning",
        "source": _clean(source) or "precheck",
        "status": _clean(status) or "open",
        "extra": json.dumps(extra or {}, ensure_ascii=False),
    }
    columns_df = execute_sql("PRAGMA table_info(import_issue_pool)")
    table_columns = {str(row["name"]) for _, row in columns_df.iterrows()}
    insert_values = {key: value for key, value in values.items() if key in table_columns}
    if not insert_values:
        return {"recorded": False, "reason": "no_supported_columns"}

    columns = ", ".join(insert_values)
    placeholders = ", ".join(f":{key}" for key in insert_values)
    session = get_session()
    try:
        session.execute(
            text(f"INSERT INTO import_issue_pool ({columns}) VALUES ({placeholders})"),
            insert_values,
        )
        session.commit()
        return {"recorded": True, "reason": "", "columns": sorted(insert_values)}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
