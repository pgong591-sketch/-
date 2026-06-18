"""Ownership and investment-percentage helpers.

`companies` describes the management hierarchy. `ownership` describes the
investment relationship and direct ownership percentage between entities.
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
from sqlalchemy import text

from .company_dimension import seed_dim_company_from_companies
from .db_connection import execute_sql, get_session


DEFAULT_EFFECTIVE_DATE = "19000101"
CONTROL_OPTIONS = ["是", "否"]


OWNERSHIP_COLUMNS = [
    "parent_code",
    "sub_code",
    "ownership_pct",
    "effective_date",
    "expiration_date",
    "is_control",
]


def ensure_ownership_table() -> None:
    """Create the ownership table and indexes for older local databases."""
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS ownership (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_code TEXT NOT NULL,
                sub_code TEXT NOT NULL,
                ownership_pct REAL NOT NULL DEFAULT 100,
                effective_date TEXT NOT NULL,
                expiration_date TEXT,
                is_control INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_code) REFERENCES companies(code),
                FOREIGN KEY (sub_code) REFERENCES companies(code),
                UNIQUE(parent_code, sub_code, effective_date)
            )
        """))
        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ownership_unique_edge
                ON ownership(parent_code, sub_code, effective_date)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ownership_parent
                ON ownership(parent_code)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ownership_sub
                ON ownership(sub_code)
        """))
        session.commit()
    finally:
        session.close()


def classify_investment(ownership_pct: object, is_control: object = 1) -> str:
    """Return the business-facing investment category."""
    try:
        pct = float(ownership_pct or 0)
    except (TypeError, ValueError):
        pct = 0
    control = _parse_control(is_control)

    if pct >= 99.999:
        return "全资子公司"
    if control and pct > 0:
        return "控股公司"
    if control:
        return "控制公司"
    if pct > 0:
        return "参股公司"
    return "未配置"


def seed_ownership_from_companies(default_pct: float = 100.0) -> int:
    """Seed missing direct ownership rows from the current hierarchy.

    The seed is only a baseline. Real partial ownership should be edited in the
    ownership grid after finance confirms the investment percentage.
    """
    ensure_ownership_table()
    session = get_session()
    inserted = 0
    try:
        _prune_ownership_orphans(session)
        rows = session.execute(text("""
            SELECT c.parent_code, c.code
            FROM companies c
            JOIN companies p ON p.code = c.parent_code
            WHERE c.status = 1
              AND c.parent_code IS NOT NULL
              AND c.parent_code <> ''
              AND c.parent_code <> 'ROOT'
              AND NOT EXISTS (
                  SELECT 1
                  FROM ownership o
                  WHERE o.parent_code = c.parent_code
                    AND o.sub_code = c.code
                    AND (o.expiration_date IS NULL OR o.expiration_date = '')
              )
            ORDER BY c.tree_path, c.code
        """)).fetchall()

        for parent_code, sub_code in rows:
            session.execute(text("""
                INSERT INTO ownership
                    (parent_code, sub_code, ownership_pct, effective_date,
                     expiration_date, is_control)
                VALUES
                    (:parent_code, :sub_code, :ownership_pct, :effective_date,
                     NULL, 1)
            """), {
                "parent_code": parent_code,
                "sub_code": sub_code,
                "ownership_pct": default_pct,
                "effective_date": DEFAULT_EFFECTIVE_DATE,
            })
            inserted += 1
        session.commit()
        return inserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def prune_ownership_orphans() -> int:
    """Remove ownership rows that reference deleted companies."""
    ensure_ownership_table()
    session = get_session()
    try:
        deleted = _prune_ownership_orphans(session)
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _prune_ownership_orphans(session) -> int:
    result = session.execute(text("""
        DELETE FROM ownership
        WHERE NOT EXISTS (
            SELECT 1 FROM companies c WHERE c.code = ownership.parent_code
        )
           OR NOT EXISTS (
            SELECT 1 FROM companies c WHERE c.code = ownership.sub_code
        )
    """))
    return result.rowcount or 0


def get_ownership_grid() -> pd.DataFrame:
    """Return the editable ownership grid with company names and dimensions."""
    seed_dim_company_from_companies()
    seed_ownership_from_companies()
    df = execute_sql("""
        SELECT
            o.id,
            o.parent_code,
            COALESCE(parent.name, '') AS parent_name,
            o.sub_code,
            COALESCE(sub.name, '') AS sub_name,
            COALESCE(dim.business_group, '') AS business_group,
            COALESCE(dim.business_type, '') AS business_type,
            o.ownership_pct,
            o.effective_date,
            COALESCE(o.expiration_date, '') AS expiration_date,
            COALESCE(o.is_control, 1) AS is_control,
            sub.tree_path
        FROM ownership o
        LEFT JOIN companies parent ON parent.code = o.parent_code
        LEFT JOIN companies sub ON sub.code = o.sub_code
        LEFT JOIN dim_company dim ON dim.company_id = o.sub_code
        ORDER BY sub.tree_path, o.parent_code, o.sub_code, o.effective_date
    """)
    if len(df) == 0:
        return pd.DataFrame(columns=[
            "parent_code",
            "parent_name",
            "sub_code",
            "sub_name",
            "business_group",
            "business_type",
            "ownership_pct",
            "investment_category",
            "effective_date",
            "expiration_date",
            "is_control",
        ])

    df["investment_category"] = df.apply(
        lambda row: classify_investment(row["ownership_pct"], row["is_control"]),
        axis=1,
    )
    df["is_control"] = df["is_control"].astype(int).map({1: "是", 0: "否"}).fillna("是")
    return df[[
        "parent_code",
        "parent_name",
        "sub_code",
        "sub_name",
        "business_group",
        "business_type",
        "ownership_pct",
        "investment_category",
        "effective_date",
        "expiration_date",
        "is_control",
    ]]


def save_ownership_grid(df: pd.DataFrame) -> int:
    """Replace ownership rows with the edited grid."""
    ensure_ownership_table()
    if df is None:
        return 0

    save_df = _normalize_columns(df)
    if len(save_df) == 0:
        return 0

    missing = [col for col in ["parent_code", "sub_code", "ownership_pct"] if col not in save_df.columns]
    if missing:
        raise ValueError(f"缺少必填列: {missing}")

    for col in OWNERSHIP_COLUMNS:
        if col not in save_df.columns:
            if col == "effective_date":
                save_df[col] = DEFAULT_EFFECTIVE_DATE
            elif col == "expiration_date":
                save_df[col] = ""
            elif col == "is_control":
                save_df[col] = "是"
            else:
                save_df[col] = ""

    save_df = save_df[OWNERSHIP_COLUMNS].copy()
    save_df["parent_code"] = save_df["parent_code"].map(_clean_code)
    save_df["sub_code"] = save_df["sub_code"].map(_clean_code)
    save_df = save_df[(save_df["parent_code"] != "") | (save_df["sub_code"] != "")]
    save_df = save_df[(save_df["parent_code"] != "") & (save_df["sub_code"] != "")]

    rows: list[dict[str, object]] = []
    for _, row in save_df.iterrows():
        parent_code = _clean_code(row["parent_code"])
        sub_code = _clean_code(row["sub_code"])
        if parent_code == sub_code:
            raise ValueError(f"投资主体和被投资主体不能相同: {parent_code}")

        pct = _parse_pct(row["ownership_pct"])
        effective_date = _normalize_date(row.get("effective_date"), DEFAULT_EFFECTIVE_DATE)
        expiration_date = _normalize_date(row.get("expiration_date"), "")
        rows.append({
            "parent_code": parent_code,
            "sub_code": sub_code,
            "ownership_pct": pct,
            "effective_date": effective_date,
            "expiration_date": expiration_date or None,
            "is_control": _parse_control(row.get("is_control")),
        })

    _validate_company_codes({row["parent_code"] for row in rows} | {row["sub_code"] for row in rows})

    deduped = {}
    for row in rows:
        key = (row["parent_code"], row["sub_code"], row["effective_date"])
        deduped[key] = row

    session = get_session()
    try:
        session.execute(text("DELETE FROM ownership"))
        for row in deduped.values():
            session.execute(text("""
                INSERT INTO ownership
                    (parent_code, sub_code, ownership_pct, effective_date,
                     expiration_date, is_control)
                VALUES
                    (:parent_code, :sub_code, :ownership_pct, :effective_date,
                     :expiration_date, :is_control)
            """), row)
        session.commit()
        return len(deduped)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "母公司编码": "parent_code",
        "投资主体编码": "parent_code",
        "子公司编码": "sub_code",
        "被投资主体编码": "sub_code",
        "投资占比(%)": "ownership_pct",
        "投资占比": "ownership_pct",
        "持股比例": "ownership_pct",
        "持股比例(%)": "ownership_pct",
        "生效日期": "effective_date",
        "失效日期": "expiration_date",
        "是否控制": "is_control",
    }
    normalized = df.rename(columns=rename_map).copy()
    keep = [col for col in normalized.columns if col in OWNERSHIP_COLUMNS]
    return normalized[keep].copy()


def _clean_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text_value = str(value).strip()
    if re.fullmatch(r"\d+\.0", text_value):
        return text_value[:-2]
    return text_value


def _parse_pct(value: object) -> float:
    try:
        pct = float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        raise ValueError(f"投资占比不是有效数字: {value!r}") from None
    if pct < 0 or pct > 100:
        raise ValueError(f"投资占比必须在 0 到 100 之间: {pct}")
    return pct


def _parse_control(value: object) -> int:
    text_value = str(value or "").strip().lower()
    return 1 if text_value in {"1", "true", "yes", "y", "是"} else 0


def _normalize_date(value: object, default: str) -> str:
    if value is None or pd.isna(value):
        return default
    if hasattr(value, "strftime"):
        return value.strftime("%Y%m%d")
    text_value = str(value).strip()
    if not text_value:
        return default
    if re.fullmatch(r"\d+\.0", text_value):
        text_value = text_value[:-2]
    digits = re.sub(r"\D", "", text_value)
    if len(digits) == 6:
        return f"{digits}01"
    if len(digits) == 8:
        return digits
    raise ValueError(f"日期格式应为 YYYYMMDD 或 YYYY-MM-DD: {value!r}")


def _validate_company_codes(codes: Iterable[str]) -> None:
    codes = {code for code in codes if code}
    if not codes:
        return
    params = {f"code_{idx}": code for idx, code in enumerate(sorted(codes))}
    placeholders = ", ".join(f":code_{idx}" for idx in range(len(params)))
    existing = execute_sql(
        f"SELECT code FROM companies WHERE code IN ({placeholders})",
        params,
    )
    existing_codes = set(existing["code"].astype(str).tolist()) if len(existing) else set()
    missing = sorted(codes - existing_codes)
    if missing:
        raise ValueError(f"股权关系引用了不存在的公司编码: {missing}")
