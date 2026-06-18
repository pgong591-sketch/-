"""Company hierarchy and organization-tree helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from .company_aliases import ensure_company_alias_table, seed_aliases_from_companies
from .db_connection import execute_sql, get_session


ROOT_CODE = "ROOT"
ROOT_NAMES = {
    ROOT_CODE,
    "root",
    "\u591a\u7ef4\u6559\u80b2\u96c6\u56e2",  # 多维教育集团
}

COL_ALIASES = {
    "code": (
        "code",
        "company_code",
        "\u516c\u53f8\u7f16\u7801",  # 公司编码
        "\u516c\u53f8\u4ee3\u7801",  # 公司代码
        "\u7f16\u7801",  # 编码
    ),
    "name": (
        "name",
        "company_name",
        "\u516c\u53f8\u540d\u79f0",  # 公司名称
        "\u540d\u79f0",  # 名称
    ),
    "parent_code": (
        "parent_code",
        "parent",
        "parent_name",
        "\u4e0a\u7ea7\u516c\u53f8",  # 上级公司
        "\u4e0a\u7ea7\u7f16\u7801",  # 上级编码
        "\u6bcd\u516c\u53f8",  # 母公司
    ),
    "short_name": (
        "short_name",
        "short",
        "alias",
        "\u7b80\u79f0",  # 简称
        "\u516c\u53f8\u7b80\u79f0",  # 公司简称
        "\u522b\u540d",  # 别名
    ),
    "industry": (
        "industry",
        "\u6240\u5c5e\u884c\u4e1a",  # 所属行业
        "\u884c\u4e1a",  # 行业
    ),
    "is_consolidated": (
        "is_consolidated",
        "consolidated",
        "\u662f\u5426\u5408\u5e76",  # 是否合并
        "\u5408\u5e76\u8303\u56f4",  # 合并范围
    ),
}


def _clean_text(value: Any, compact: bool = True) -> str:
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip()
    if value.lower() in {"nan", "none"}:
        return ""
    if compact:
        return re.sub(r"\s+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_code(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    code = str(value).strip()
    if re.fullmatch(r"\d+\.0", code):
        return code[:-2]
    return code


def _parse_bool(value: Any, default: int = 1) -> int:
    raw = _clean_text(value, compact=False).lower()
    if raw in {"0", "false", "no", "n", "\u5426", "\u4e0d\u5408\u5e76"}:
        return 0
    if raw in {"1", "true", "yes", "y", "\u662f", "\u5408\u5e76"}:
        return 1
    return default


def _column_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for canonical, aliases in COL_ALIASES.items():
        for alias in aliases:
            lookup[_clean_text(alias, compact=False).lower()] = canonical
    return lookup


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = _column_lookup()
    rename = {}
    for col in df.columns:
        normalized = _clean_text(col, compact=False).lower()
        if normalized in lookup:
            rename[col] = lookup[normalized]
    return df.rename(columns=rename)


def _find_header_row(df_raw: pd.DataFrame) -> Optional[int]:
    code_aliases = {
        _clean_text(alias, compact=False).lower()
        for alias in COL_ALIASES["code"]
    }
    name_aliases = {
        _clean_text(alias, compact=False).lower()
        for alias in COL_ALIASES["name"]
    }
    for idx in range(min(25, len(df_raw))):
        values = {
            _clean_text(value, compact=False).lower()
            for value in df_raw.iloc[idx].tolist()
            if _clean_text(value, compact=False)
        }
        if values & code_aliases and values & name_aliases:
            return idx
    return None


def _valid_company_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "code" not in df.columns:
        return df.iloc[0:0]
    result = df.copy()
    result["code"] = result["code"].apply(_clean_code)
    result = result[result["code"] != ""]
    footer_pattern = re.compile("(?:\u5236\u8868|\u7b2c.*\u9875|\u5408\u8ba1|\u603b\u8ba1)")
    result = result[~result["code"].astype(str).str.contains(footer_pattern, na=False, regex=True)]
    return result


def _ensure_root_company(session, root_name: str) -> None:
    existing = session.execute(
        text("SELECT code FROM companies WHERE code = :code"),
        {"code": ROOT_CODE},
    ).fetchone()
    if existing:
        session.execute(
            text("""
                UPDATE companies
                SET name = COALESCE(NULLIF(name, ''), :name),
                    short_name = COALESCE(NULLIF(short_name, ''), :name),
                    parent_code = NULL,
                    status = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE code = :code
            """),
            {"code": ROOT_CODE, "name": root_name},
        )
        return

    session.execute(
        text("""
            INSERT INTO companies
                (code, name, short_name, parent_code, level, tree_path,
                 is_leaf, is_consolidated, status)
            VALUES
                (:code, :name, :name, NULL, 0, :path, 0, 1, 1)
        """),
        {"code": ROOT_CODE, "name": root_name, "path": f"/{ROOT_CODE}"},
    )


def _resolve_parent_code(
    raw_parent: str,
    in_file_aliases: Dict[str, str],
    existing_aliases: Dict[str, str],
) -> Optional[str]:
    parent = _clean_text(raw_parent)
    if not parent:
        return None
    if parent in ROOT_NAMES or parent.lower() in ROOT_NAMES:
        return ROOT_CODE
    if parent in in_file_aliases:
        return in_file_aliases[parent]
    if parent in existing_aliases:
        return existing_aliases[parent]
    return None


def rebuild_tree_path(root_code: str = ROOT_CODE) -> None:
    """Rebuild materialized tree paths and levels for the company forest."""
    session = get_session()
    try:
        session.execute(text("UPDATE companies SET tree_path = NULL, level = 0"))

        roots: List[str] = []
        requested = session.execute(
            text("SELECT code FROM companies WHERE code = :code"),
            {"code": root_code},
        ).fetchone()
        if requested:
            roots.append(str(requested[0]))

        rows = session.execute(text("""
            SELECT code
            FROM companies
            WHERE parent_code IS NULL OR parent_code = ''
            ORDER BY code
        """)).fetchall()
        for row in rows:
            code = str(row[0])
            if code not in roots:
                roots.append(code)

        if not roots:
            rows = session.execute(text("""
                SELECT c.code
                FROM companies c
                LEFT JOIN companies p ON c.parent_code = p.code
                WHERE c.parent_code IS NOT NULL
                  AND c.parent_code <> ''
                  AND p.code IS NULL
                ORDER BY c.code
            """)).fetchall()
            roots = [str(row[0]) for row in rows]

        visited: set[str] = set()
        for root in roots:
            if root in visited:
                continue
            root_path = f"/{root}"
            session.execute(
                text("UPDATE companies SET tree_path = :path, level = 0 WHERE code = :code"),
                {"path": root_path, "code": root},
            )
            visited.add(root)
            _update_tree_path_recursive(session, root, root_path, 0, visited)

        session.execute(text("""
            UPDATE companies SET is_leaf = 1
            WHERE code NOT IN (
                SELECT DISTINCT parent_code FROM companies
                WHERE parent_code IS NOT NULL AND parent_code != ''
            )
        """))
        session.execute(text("""
            UPDATE companies SET is_leaf = 0
            WHERE code IN (
                SELECT DISTINCT parent_code FROM companies
                WHERE parent_code IS NOT NULL AND parent_code != ''
            )
        """))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_tree_path_recursive(
    session,
    parent_code: str,
    parent_path: str,
    level: int,
    visited: Optional[set[str]] = None,
) -> None:
    """Recursively update child tree paths."""
    visited = visited or set()
    children = session.execute(
        text("SELECT code FROM companies WHERE parent_code = :parent ORDER BY code"),
        {"parent": parent_code},
    ).fetchall()

    for child in children:
        child_code = str(child[0])
        if child_code in visited:
            raise ValueError(f"Cycle detected in company hierarchy at {child_code!r}")
        child_path = f"{parent_path}/{child_code}"
        child_level = level + 1
        session.execute(
            text("UPDATE companies SET tree_path = :path, level = :level WHERE code = :code"),
            {"path": child_path, "level": child_level, "code": child_code},
        )
        visited.add(child_code)
        _update_tree_path_recursive(session, child_code, child_path, child_level, visited)


def get_subtree(company_code: str, include_self: bool = True) -> pd.DataFrame:
    """Return one company and all descendants."""
    company = get_company_info(company_code)
    if company is None:
        return pd.DataFrame()

    tree_path = company.get("tree_path", "")
    if tree_path:
        df = execute_sql(
            """
            SELECT * FROM companies
            WHERE tree_path LIKE :pattern OR tree_path = :tree_path
            ORDER BY tree_path
            """,
            {"pattern": f"{tree_path}/%", "tree_path": tree_path},
        )
    else:
        df = execute_sql(
            """
            WITH RECURSIVE subtree AS (
                SELECT * FROM companies WHERE code = :code
                UNION ALL
                SELECT c.* FROM companies c
                JOIN subtree s ON c.parent_code = s.code
            )
            SELECT * FROM subtree ORDER BY tree_path
            """,
            {"code": company_code},
        )

    if not include_self and len(df) > 0:
        df = df[df["code"] != company_code]
    return df


def get_company_info(company_code: str) -> Optional[Dict[str, Any]]:
    """Return one company row as a dict."""
    df = execute_sql("SELECT * FROM companies WHERE code = :code", {"code": company_code})
    if len(df) > 0:
        return df.iloc[0].to_dict()
    return None


def get_ancestors(company_code: str) -> pd.DataFrame:
    """Return all ancestors from root to parent."""
    company = get_company_info(company_code)
    if company is None or not company.get("tree_path"):
        return pd.DataFrame()

    nodes = str(company["tree_path"]).strip("/").split("/")
    if len(nodes) <= 1:
        return pd.DataFrame()

    placeholders = ", ".join(f":code_{idx}" for idx, _ in enumerate(nodes[:-1]))
    params = {f"code_{idx}": code for idx, code in enumerate(nodes[:-1])}
    return execute_sql(
        f"SELECT * FROM companies WHERE code IN ({placeholders}) ORDER BY level",
        params,
    )


def get_company_list_for_summary(company_code: str) -> List[str]:
    """Return a company-code list for hierarchy summary queries."""
    subtree = get_subtree(company_code, include_self=True)
    if len(subtree) == 0:
        return [company_code]
    return subtree["code"].tolist()


def get_summary_report(
    company_code: str,
    period: str,
    table: str = "account_balance",
    sum_columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Sum financial rows across a company subtree."""
    companies = get_company_list_for_summary(company_code)
    if not companies:
        return pd.DataFrame()

    sample = execute_sql(f"SELECT * FROM {table} LIMIT 1")
    if len(sample) == 0:
        return pd.DataFrame()

    exclude = {
        "id",
        "level",
        "is_consolidated",
        "status",
        "is_locked",
        "is_internal",
        "is_leaf",
    }
    numeric_cols = [
        col
        for col in sample.select_dtypes(include=["float64", "int64"]).columns
        if col not in exclude
    ]
    sum_cols = [col for col in (sum_columns or numeric_cols) if col in sample.columns]
    group_cols = [
        col
        for col in ["account_code", "account_name", "direction", "item_code", "item_name", "category"]
        if col in sample.columns
    ]
    if not sum_cols or not group_cols:
        return pd.DataFrame()

    company_params = {f"company_{idx}": code for idx, code in enumerate(companies)}
    placeholders = ", ".join(f":company_{idx}" for idx, _ in enumerate(companies))
    sum_str = ", ".join(f"SUM({col}) AS {col}" for col in sum_cols)
    group_str = ", ".join(group_cols)
    order_by = group_cols[0]

    sql = f"""
        SELECT {group_str}, {sum_str}
        FROM {table}
        WHERE company_code IN ({placeholders}) AND period = :period
        GROUP BY {group_str}
        ORDER BY {order_by}
    """
    return execute_sql(sql, {"period": period, **company_params})


def import_companies_from_excel(file_path: str) -> Dict[str, Any]:
    """Import company hierarchy and source-name aliases from an Excel file."""
    result: Dict[str, Any] = {
        "success": False,
        "total": 0,
        "inserted": 0,
        "updated": 0,
        "aliases_seeded": 0,
        "errors": [],
    }

    try:
        df_raw = pd.read_excel(file_path, header=None)
        header_row = _find_header_row(df_raw)
        df = pd.read_excel(file_path, header=header_row) if header_row is not None else pd.read_excel(file_path)
        df = df.dropna(axis=1, how="all").dropna(how="all")
        df = _rename_columns(df)

        missing = [col for col in ["code", "name"] if col not in df.columns]
        if missing:
            result["errors"].append(
                f"Missing required columns: {missing}; current columns: {list(df.columns)}"
            )
            return result

        df = _valid_company_rows(df)
        if len(df) == 0:
            result["errors"].append("No valid company rows found.")
            return result

        in_file_aliases: Dict[str, str] = {}
        parent_values: List[str] = []
        for _, row in df.iterrows():
            code = _clean_code(row.get("code"))
            name = _clean_text(row.get("name"))
            short_name = _clean_text(row.get("short_name")) if "short_name" in df.columns else ""
            parent = _clean_text(row.get("parent_code")) if "parent_code" in df.columns else ""
            if parent:
                parent_values.append(parent)
            for alias in {code, name, short_name}:
                if alias:
                    in_file_aliases[alias] = code

        root_names = [parent for parent in parent_values if parent not in in_file_aliases]
        root_name = root_names[0] if root_names else "\u591a\u7ef4\u6559\u80b2\u96c6\u56e2"
        ROOT_NAMES.add(root_name)

        ensure_company_alias_table()
        alias_df = execute_sql("SELECT alias, company_code FROM company_aliases WHERE status = 1")
        existing_aliases = {
            _clean_text(row["alias"]): _clean_code(row["company_code"])
            for _, row in alias_df.iterrows()
        }

        session = get_session()
        try:
            _ensure_root_company(session, root_name)

            for _, row in df.iterrows():
                code = _clean_code(row.get("code"))
                name = _clean_text(row.get("name")) or code
                short_name = _clean_text(row.get("short_name")) if "short_name" in df.columns else ""
                industry = _clean_text(row.get("industry")) if "industry" in df.columns else ""
                parent_raw = _clean_text(row.get("parent_code")) if "parent_code" in df.columns else ""
                parent_code = _resolve_parent_code(parent_raw, in_file_aliases, existing_aliases)
                is_consolidated = _parse_bool(row.get("is_consolidated"), 1)

                existing = session.execute(
                    text("SELECT code FROM companies WHERE code = :code"),
                    {"code": code},
                ).fetchone()
                if existing:
                    session.execute(
                        text("""
                            UPDATE companies
                            SET name = :name,
                                short_name = :short_name,
                                parent_code = :parent_code,
                                is_consolidated = :is_consolidated,
                                industry = COALESCE(NULLIF(:industry, ''), industry),
                                status = 1,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE code = :code
                        """),
                        {
                            "code": code,
                            "name": name,
                            "short_name": short_name or name,
                            "parent_code": parent_code,
                            "is_consolidated": is_consolidated,
                            "industry": industry,
                        },
                    )
                    result["updated"] += 1
                else:
                    session.execute(
                        text("""
                            INSERT INTO companies
                                (code, name, short_name, parent_code, level,
                                 is_consolidated, status, industry)
                            VALUES
                                (:code, :name, :short_name, :parent_code, 1,
                                 :is_consolidated, 1, NULLIF(:industry, ''))
                        """),
                        {
                            "code": code,
                            "name": name,
                            "short_name": short_name or name,
                            "parent_code": parent_code,
                            "is_consolidated": is_consolidated,
                            "industry": industry,
                        },
                    )
                    result["inserted"] += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        rebuild_tree_path(ROOT_CODE)
        result["aliases_seeded"] = seed_aliases_from_companies()
        result["success"] = True
        result["total"] = len(df)
        return result
    except Exception as exc:
        result["errors"].append(str(exc))
        return result


def get_company_tree() -> pd.DataFrame:
    """Return the company tree ordered by materialized path."""
    df = execute_sql("""
        SELECT code, name, parent_code, level, tree_path,
               is_leaf, is_consolidated, status
        FROM companies
        ORDER BY tree_path
    """)
    if len(df) > 0 and "tree_path" in df.columns:
        df["display_name"] = df.apply(
            lambda row: (
                "  " * int(row["level"]) + f"- {row['name']}"
                if int(row["level"]) > 0
                else str(row["name"])
            ),
            axis=1,
        )
    return df
