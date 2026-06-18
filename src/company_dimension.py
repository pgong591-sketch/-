"""Company dimension table helpers.

`companies` remains the hierarchy master. `dim_company` stores editable
business attributes used by dashboards, warning reports, and future
consolidation rules.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import text

from .db_connection import execute_sql, get_session


MANAGED_BUSINESS_GROUP_OPTIONS = [
    "非学科素质中心模块",
    "尔遇书馆模块",
    "学校模块",
    "幼儿园模块",
    "托育模块",
    "文旅模块",
    "尔遇书城模块",
    "少年宫模块",
    "国际教育模块",
    "职能公司模块",
    "物业公司",
    "外部投资模块",
]
BUSINESS_GROUP_OPTIONS = [""] + MANAGED_BUSINESS_GROUP_OPTIONS
LEGACY_BUSINESS_GROUP_MAP = {
    "素质板块": "非学科素质中心模块",
    "书馆板块": "尔遇书馆模块",
    "幼儿园板块": "幼儿园模块",
    "教育板块": "",
    "总部及辅助": "职能公司模块",
    "对外投资项目": "外部投资模块",
    "其他实控公司": "",
    "其他": "",
}
BUSINESS_TYPE_OPTIONS = ["", "集团", "管理中心", "小学", "初中", "高中", "个性化", "校区", "幼儿园", "托育", "书店", "书馆", "物业", "科技公司", "文旅", "健康管理", "其他"]
REGION_OPTIONS = ["", "东莞", "莞城", "南城", "东城", "万江", "西平", "深圳", "茶山", "石龙", "厚街", "石碣", "虎门", "石井", "东泰", "寮步", "长安", "高埗", "松山湖", "望牛墩", "其他"]
OPERATIONAL_OPTIONS = ["是", "否"]


DIM_COMPANY_COLUMNS = [
    "company_id",
    "company_name",
    "business_group",
    "business_type",
    "region",
    "is_operational",
]


def ensure_dim_company_table() -> None:
    """Create `dim_company` for databases created before the table existed."""
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS dim_company (
                company_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                business_group TEXT,
                business_type TEXT,
                region TEXT,
                is_operational INTEGER DEFAULT 1,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(code)
            )
        """))
        session.commit()
    finally:
        session.close()


def infer_business_group(company_id: str, name: str, parent_code: str | None = None) -> str:
    text_value = f"{company_id} {name} {parent_code or ''}"
    if "托育" in text_value:
        return "托育模块"
    if "少年宫" in text_value:
        return "少年宫模块"
    if any(token in text_value for token in ["书城", "书店"]):
        return "尔遇书城模块"
    if "尔遇" in text_value or "书馆" in text_value or company_id.startswith("10204"):
        return "尔遇书馆模块"
    if "幼儿" in text_value or company_id.startswith("10107"):
        return "幼儿园模块"
    if any(token in text_value for token in ["文旅", "探幽"]):
        return "文旅模块"
    if "国际" in text_value or company_id.startswith("10102"):
        return "国际教育模块"
    if any(token in text_value for token in ["非学科", "素质", "虎翼营", "拔创", "校区"]):
        return "非学科素质中心模块"
    if "多维学校" in text_value:
        return "学校模块"
    if "物业" in text_value:
        return "物业公司"
    if any(token in text_value for token in ["集团", "管理中心", "科技", "职能"]):
        return "职能公司模块"
    return ""


def infer_business_type(name: str) -> str:
    if "集团" in name:
        return "集团"
    if "管理中心" in name:
        return "管理中心"
    if "小学" in name:
        return "小学"
    if "初中" in name:
        return "初中"
    if "高中" in name:
        return "高中"
    if "个性化" in name:
        return "个性化"
    if "幼儿" in name:
        return "幼儿园"
    if "托育" in name:
        return "托育"
    if "书馆" in name:
        return "书馆"
    if "书店" in name:
        return "书店"
    if "物业" in name:
        return "物业"
    if "科技" in name:
        return "科技公司"
    if "文旅" in name:
        return "文旅"
    if "健康" in name:
        return "健康管理"
    if "校区" in name:
        return "校区"
    return "其他"


def infer_region(name: str) -> str:
    regions = ["松山湖", "望牛墩", "莞城", "南城", "东城", "万江", "西平", "深圳", "茶山", "石龙", "厚街", "石碣", "虎门", "石井", "东泰", "寮步", "长安", "高埗"]
    for region in regions:
        if region in name:
            return region
    if "东莞" in name:
        return "东莞"
    return ""


def infer_is_operational(name: str, level: object = None) -> int:
    if any(token in name for token in ["集团", "管理中心"]):
        return 0
    try:
        return 1 if int(level or 0) >= 3 else 0
    except (TypeError, ValueError):
        return 1


def seed_dim_company_from_companies() -> int:
    """Insert missing company dimension rows from `companies`."""
    ensure_dim_company_table()
    session = get_session()
    inserted = 0
    try:
        rows = session.execute(text("""
            SELECT c.code, c.name, c.parent_code, c.level
            FROM companies c
            LEFT JOIN dim_company d ON d.company_id = c.code
            WHERE d.company_id IS NULL
            ORDER BY c.code
        """)).fetchall()

        for company_id, name, parent_code, level in rows:
            session.execute(text("""
                INSERT INTO dim_company
                    (company_id, company_name, business_group, business_type,
                     region, is_operational, update_time)
                VALUES
                    (:company_id, :company_name, :business_group, :business_type,
                     :region, :is_operational, CURRENT_TIMESTAMP)
            """), {
                "company_id": company_id,
                "company_name": name,
                "business_group": infer_business_group(str(company_id), str(name or ""), parent_code),
                "business_type": infer_business_type(str(name or "")),
                "region": infer_region(str(name or "")),
                "is_operational": infer_is_operational(str(name or ""), level),
            })
            inserted += 1
        session.commit()
        return inserted
    finally:
        session.close()


def sync_dim_company_names() -> int:
    """Keep readonly dimension names aligned with companies."""
    ensure_dim_company_table()
    session = get_session()
    try:
        result = session.execute(text("""
            UPDATE dim_company
            SET company_name = (
                    SELECT c.name FROM companies c WHERE c.code = dim_company.company_id
                ),
                update_time = CURRENT_TIMESTAMP
            WHERE EXISTS (
                SELECT 1 FROM companies c
                WHERE c.code = dim_company.company_id
                  AND c.name <> dim_company.company_name
            )
        """))
        session.commit()
        return result.rowcount or 0
    finally:
        session.close()


def prune_dim_company_orphans() -> int:
    """Remove dimension rows whose company no longer exists."""
    ensure_dim_company_table()
    session = get_session()
    try:
        result = session.execute(text("""
            DELETE FROM dim_company
            WHERE NOT EXISTS (
                SELECT 1
                FROM companies c
                WHERE c.code = dim_company.company_id
            )
        """))
        session.commit()
        return result.rowcount or 0
    finally:
        session.close()


def get_company_dimensions() -> pd.DataFrame:
    """Return the editable company dimension grid."""
    prune_dim_company_orphans()
    seed_dim_company_from_companies()
    sync_dim_company_names()
    df = execute_sql("""
        SELECT
            d.company_id,
            d.company_name,
            COALESCE(d.business_group, '') AS business_group,
            COALESCE(d.business_type, '') AS business_type,
            COALESCE(d.region, '') AS region,
            COALESCE(d.is_operational, 1) AS is_operational,
            c.parent_code,
            c.level,
            c.tree_path
        FROM dim_company d
        LEFT JOIN companies c ON c.code = d.company_id
        ORDER BY c.tree_path, d.company_id
    """)
    if len(df) > 0:
        df["business_group"] = df["business_group"].map(normalize_business_group)
        df["is_operational"] = df["is_operational"].astype(int).map({1: "是", 0: "否"}).fillna("是")
    return df


def normalize_business_group(value: object) -> str:
    """Normalize historical board names to the current controlled options."""
    text_value = str(value or "").strip()
    if text_value in BUSINESS_GROUP_OPTIONS:
        return text_value
    return LEGACY_BUSINESS_GROUP_MAP.get(text_value, "")


def _normalize_option(value: object, options: Iterable[str], default: str = "") -> str:
    text_value = str(value or "").strip()
    return text_value if text_value in options else default


def save_company_dimensions(df: pd.DataFrame) -> int:
    """Replace `dim_company` with the edited grid."""
    ensure_dim_company_table()
    if df is None:
        return 0

    save_df = df.copy()
    rename_map = {
        "公司编码": "company_id",
        "公司名称": "company_name",
        "所属板块": "business_group",
        "业态类型": "business_type",
        "所属区域": "region",
        "运营主体": "is_operational",
    }
    save_df = save_df.rename(columns=rename_map)
    missing = [col for col in ["company_id", "company_name"] if col not in save_df.columns]
    if missing:
        raise ValueError(f"缺少必填列: {missing}")

    save_df = save_df[[col for col in DIM_COMPANY_COLUMNS if col in save_df.columns]].copy()
    save_df["company_id"] = save_df["company_id"].astype(str).str.strip()
    save_df["company_name"] = save_df["company_name"].astype(str).str.strip()
    save_df = save_df[(save_df["company_id"] != "") & (save_df["company_name"] != "")]
    save_df = save_df.drop_duplicates(subset=["company_id"], keep="last")
    for col, default in [
        ("business_group", ""),
        ("business_type", ""),
        ("region", ""),
        ("is_operational", "是"),
    ]:
        if col not in save_df.columns:
            save_df[col] = default

    save_df["business_group"] = save_df["business_group"].map(
        normalize_business_group
    )
    save_df["business_type"] = save_df["business_type"].map(
        lambda value: _normalize_option(value, BUSINESS_TYPE_OPTIONS)
    )
    save_df["region"] = save_df["region"].map(
        lambda value: _normalize_option(value, REGION_OPTIONS)
    )
    save_df["is_operational"] = save_df["is_operational"].map(
        lambda value: 1 if str(value).strip() in ("1", "是", "true", "True") else 0
    )

    session = get_session()
    try:
        session.execute(text("DELETE FROM dim_company"))
        for _, row in save_df.iterrows():
            session.execute(text("""
                INSERT INTO dim_company
                    (company_id, company_name, business_group, business_type,
                     region, is_operational, update_time)
                VALUES
                    (:company_id, :company_name, :business_group, :business_type,
                     :region, :is_operational, CURRENT_TIMESTAMP)
            """), {
                "company_id": row["company_id"],
                "company_name": row["company_name"],
                "business_group": row.get("business_group", ""),
                "business_type": row.get("business_type", ""),
                "region": row.get("region", ""),
                "is_operational": int(row.get("is_operational", 1)),
            })
        session.commit()
        return len(save_df)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
