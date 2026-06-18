"""Account standardization and mapping helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from .db_connection import execute_sql, get_session


STANDARD_ACCOUNTS_SQL = """
CREATE TABLE IF NOT EXISTS standard_accounts (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    balance_direction TEXT DEFAULT '借',
    level           INTEGER DEFAULT 1,
    parent_code     TEXT,
    is_leaf         INTEGER DEFAULT 1,
    status          INTEGER DEFAULT 1,
    sort_order      INTEGER DEFAULT 0,
    FOREIGN KEY (parent_code) REFERENCES standard_accounts(code)
)
"""

ACCOUNT_MAPPING_SQL = """
CREATE TABLE IF NOT EXISTS account_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    local_code      TEXT NOT NULL,
    local_name      TEXT,
    standard_code   TEXT NOT NULL,
    standard_name   TEXT,
    mapping_type    TEXT DEFAULT '精确映射',
    effective_from  TEXT,
    effective_to    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, local_code)
)
"""


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if pd.isna(value):
        return default
    return str(value).strip()


def ensure_account_standardization_schema() -> None:
    """Ensure account standardization tables and indexes exist."""
    session = get_session()
    try:
        session.execute(text(STANDARD_ACCOUNTS_SQL))
        session.execute(text(ACCOUNT_MAPPING_SQL))
        session.execute(
            text("CREATE INDEX IF NOT EXISTS idx_account_mapping_company ON account_mapping(company_code)")
        )
        session.execute(
            text("CREATE INDEX IF NOT EXISTS idx_account_mapping_standard ON account_mapping(standard_code)")
        )
        session.commit()
    finally:
        session.close()


def get_standard_accounts() -> pd.DataFrame:
    """Read standard account definitions."""
    ensure_account_standardization_schema()
    return execute_sql(
        """
        SELECT
            code AS 标准科目编码,
            name AS 标准科目名称,
            category AS 科目类别,
            balance_direction AS 余额方向,
            level AS 层级,
            parent_code AS 上级科目编码,
            is_leaf AS 是否末级,
            status AS 状态,
            sort_order AS 排序
        FROM standard_accounts
        ORDER BY sort_order, code
        """
    )


def upsert_standard_account(row: dict) -> None:
    """Create or update one standard account."""
    ensure_account_standardization_schema()
    code = _clean(row.get("code") or row.get("标准科目编码"))
    name = _clean(row.get("name") or row.get("标准科目名称"))
    category = _clean(row.get("category") or row.get("科目类别"), "未分类")
    if not code or not name:
        raise ValueError("标准科目编码和名称不能为空")

    params = {
        "code": code,
        "name": name,
        "category": category,
        "balance_direction": _clean(row.get("balance_direction") or row.get("余额方向"), "借"),
        "level": int(float(row.get("level") or row.get("层级") or 1)),
        "parent_code": _clean(row.get("parent_code") or row.get("上级科目编码")) or None,
        "is_leaf": int(float(row.get("is_leaf") or row.get("是否末级") or 1)),
        "status": int(float(row.get("status") or row.get("状态") or 1)),
        "sort_order": int(float(row.get("sort_order") or row.get("排序") or 0)),
    }
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO standard_accounts (
                    code, name, category, balance_direction,
                    level, parent_code, is_leaf, status, sort_order
                )
                VALUES (
                    :code, :name, :category, :balance_direction,
                    :level, :parent_code, :is_leaf, :status, :sort_order
                )
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    balance_direction = excluded.balance_direction,
                    level = excluded.level,
                    parent_code = excluded.parent_code,
                    is_leaf = excluded.is_leaf,
                    status = excluded.status,
                    sort_order = excluded.sort_order
                """
            ),
            params,
        )
        session.commit()
    finally:
        session.close()


def get_account_mappings(company_code: str | None = None) -> pd.DataFrame:
    """Read local-account to standard-account mappings."""
    ensure_account_standardization_schema()
    params: dict[str, Any] = {}
    where_clause = "1=1"
    if company_code:
        where_clause = "m.company_code = :company_code"
        params["company_code"] = company_code
    return execute_sql(
        f"""
        SELECT
            m.company_code AS 公司编码,
            COALESCE(c.name, CASE WHEN m.company_code = 'ALL' THEN '全局映射' ELSE m.company_code END) AS 公司名称,
            m.local_code AS 原始科目编码,
            m.local_name AS 原始科目名称,
            m.standard_code AS 标准科目编码,
            COALESCE(sa.name, m.standard_name) AS 标准科目名称,
            COALESCE(sa.category, '') AS 科目类别,
            m.mapping_type AS 映射类型,
            m.effective_from AS 生效期间,
            m.effective_to AS 失效期间,
            m.created_at AS 创建时间
        FROM account_mapping m
        LEFT JOIN companies c ON c.code = m.company_code
        LEFT JOIN standard_accounts sa ON sa.code = m.standard_code
        WHERE {where_clause}
        ORDER BY m.company_code, m.local_code
        """,
        params,
    )


def upsert_account_mapping(row: dict) -> None:
    """Create or update one local-account mapping."""
    ensure_account_standardization_schema()
    company_code = _clean(row.get("company_code") or row.get("公司编码"), "ALL")
    local_code = _clean(row.get("local_code") or row.get("原始科目编码"))
    standard_code = _clean(row.get("standard_code") or row.get("标准科目编码"))
    if not company_code:
        company_code = "ALL"
    if not local_code or not standard_code:
        raise ValueError("公司编码、原始科目编码、标准科目编码不能为空")

    standard_name = _clean(row.get("standard_name") or row.get("标准科目名称"))
    if not standard_name:
        standard = execute_sql(
            "SELECT name FROM standard_accounts WHERE code = :code",
            {"code": standard_code},
        )
        if len(standard):
            standard_name = str(standard.iloc[0]["name"])

    params = {
        "company_code": company_code,
        "local_code": local_code,
        "local_name": _clean(row.get("local_name") or row.get("原始科目名称")),
        "standard_code": standard_code,
        "standard_name": standard_name,
        "mapping_type": _clean(row.get("mapping_type") or row.get("映射类型"), "精确映射"),
        "effective_from": _clean(row.get("effective_from") or row.get("生效期间")) or None,
        "effective_to": _clean(row.get("effective_to") or row.get("失效期间")) or None,
    }
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO account_mapping (
                    company_code, local_code, local_name, standard_code,
                    standard_name, mapping_type, effective_from, effective_to
                )
                VALUES (
                    :company_code, :local_code, :local_name, :standard_code,
                    :standard_name, :mapping_type, :effective_from, :effective_to
                )
                ON CONFLICT(company_code, local_code) DO UPDATE SET
                    local_name = excluded.local_name,
                    standard_code = excluded.standard_code,
                    standard_name = excluded.standard_name,
                    mapping_type = excluded.mapping_type,
                    effective_from = excluded.effective_from,
                    effective_to = excluded.effective_to
                """
            ),
            params,
        )
        session.commit()
    finally:
        session.close()


def _account_filters(period: str | None, company_code: str | None) -> tuple[str, dict[str, Any]]:
    conditions = []
    params: dict[str, Any] = {}
    if period:
        conditions.append("ab.period = :period")
        params["period"] = str(period).strip()
    if company_code:
        conditions.append("ab.company_code = :company_code")
        params["company_code"] = str(company_code).strip()
    return (" AND ".join(conditions) if conditions else "1=1"), params


def find_unmapped_accounts(period: str | None = None, company_code: str | None = None) -> pd.DataFrame:
    """Find account_balance accounts without company or global mapping."""
    ensure_account_standardization_schema()
    where_clause, params = _account_filters(period, company_code)
    return execute_sql(
        f"""
        SELECT
            ab.company_code AS 公司编码,
            COALESCE(c.name, ab.company_code) AS 公司名称,
            ab.period AS 期间,
            ab.account_code AS 原始科目编码,
            ab.account_name AS 原始科目名称,
            COUNT(*) AS 记录数,
            SUM(COALESCE(ab.ending_balance, 0)) AS 期末余额
        FROM account_balance ab
        LEFT JOIN companies c ON c.code = ab.company_code
        WHERE {where_clause}
          AND NOT EXISTS (
              SELECT 1
              FROM account_mapping m
              WHERE m.local_code = ab.account_code
                AND m.company_code IN (ab.company_code, 'ALL')
                AND (m.effective_from IS NULL OR m.effective_from = '' OR m.effective_from <= ab.period)
                AND (m.effective_to IS NULL OR m.effective_to = '' OR m.effective_to >= ab.period)
          )
        GROUP BY ab.company_code, c.name, ab.period, ab.account_code, ab.account_name
        ORDER BY ab.company_code, ab.period, ab.account_code
        """,
        params,
    )


def suggest_account_mappings(period: str | None = None, company_code: str | None = None) -> pd.DataFrame:
    """Suggest mappings from history, same account name, or exact standard code."""
    unmapped = find_unmapped_accounts(period, company_code)
    if len(unmapped) == 0:
        return unmapped

    mappings = get_account_mappings()
    standards = get_standard_accounts()
    suggestions = []
    for _, row in unmapped.iterrows():
        local_code = str(row["原始科目编码"])
        local_name = str(row["原始科目名称"])
        suggestion_code = ""
        suggestion_name = ""
        reason = ""

        same_code = mappings[mappings["原始科目编码"].astype(str) == local_code]
        if len(same_code):
            hit = same_code.iloc[0]
            suggestion_code = str(hit["标准科目编码"])
            suggestion_name = str(hit["标准科目名称"])
            reason = "其他公司同编码历史映射"
        else:
            same_name = mappings[mappings["原始科目名称"].astype(str) == local_name]
            if len(same_name):
                hit = same_name.iloc[0]
                suggestion_code = str(hit["标准科目编码"])
                suggestion_name = str(hit["标准科目名称"])
                reason = "其他公司同名称历史映射"
            else:
                same_standard_code = standards[standards["标准科目编码"].astype(str) == local_code]
                if len(same_standard_code):
                    hit = same_standard_code.iloc[0]
                    suggestion_code = str(hit["标准科目编码"])
                    suggestion_name = str(hit["标准科目名称"])
                    reason = "与标准科目编码一致"

        item = row.to_dict()
        item.update(
            {
                "建议标准科目编码": suggestion_code,
                "建议标准科目名称": suggestion_name,
                "建议原因": reason,
            }
        )
        suggestions.append(item)
    return pd.DataFrame(suggestions)


def get_mapping_coverage(period: str | None = None, company_code: str | None = None) -> dict[str, Any]:
    """Calculate mapping coverage for account_balance accounts."""
    ensure_account_standardization_schema()
    where_clause, params = _account_filters(period, company_code)
    total_df = execute_sql(
        f"""
        SELECT COUNT(*) AS total_accounts
        FROM (
            SELECT DISTINCT ab.company_code, ab.account_code
            FROM account_balance ab
            WHERE {where_clause}
        ) x
        """,
        params,
    )
    mapped_df = execute_sql(
        f"""
        SELECT COUNT(*) AS mapped_accounts
        FROM (
            SELECT DISTINCT ab.company_code, ab.account_code
            FROM account_balance ab
            WHERE {where_clause}
              AND EXISTS (
                  SELECT 1
                  FROM account_mapping m
                  WHERE m.local_code = ab.account_code
                    AND m.company_code IN (ab.company_code, 'ALL')
                    AND (m.effective_from IS NULL OR m.effective_from = '' OR m.effective_from <= ab.period)
                    AND (m.effective_to IS NULL OR m.effective_to = '' OR m.effective_to >= ab.period)
              )
        ) x
        """,
        params,
    )
    total = int(total_df.iloc[0]["total_accounts"]) if len(total_df) else 0
    mapped = int(mapped_df.iloc[0]["mapped_accounts"]) if len(mapped_df) else 0
    unmapped = max(total - mapped, 0)
    coverage = mapped / total if total else 0.0
    if total == 0:
        level = "暂无数据"
    elif coverage >= 1:
        level = "正常"
    elif coverage >= 0.95:
        level = "关注"
    else:
        level = "待处理"
    return {
        "total_accounts": total,
        "mapped_accounts": mapped,
        "unmapped_accounts": unmapped,
        "coverage_rate": coverage,
        "level": level,
    }
