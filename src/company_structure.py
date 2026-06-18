"""Business-facing company structure view helpers."""

from __future__ import annotations

import pandas as pd

from .company_dimension import normalize_business_group, seed_dim_company_from_companies
from .db_connection import execute_sql
from .ownership import classify_investment, seed_ownership_from_companies


MANAGED_CATEGORY = "实控公司"
EXTERNAL_CATEGORY = "对外投资公司"

MANAGED_MODULES = [
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
]
FALLBACK_MANAGED_MODULE = "未分配模块"
EXTERNAL_MODULE = "单项目"


def get_company_structure_view() -> pd.DataFrame:
    """Return companies grouped by management category and business module."""
    seed_dim_company_from_companies()
    seed_ownership_from_companies()

    df = execute_sql("""
        WITH active_ownership AS (
            SELECT parent_code, sub_code, ownership_pct, is_control
            FROM ownership
            WHERE expiration_date IS NULL OR expiration_date = ''
        ),
        ownership_summary AS (
            SELECT
                sub_code,
                GROUP_CONCAT(parent_code, ' / ') AS investor_codes,
                MAX(COALESCE(ownership_pct, 0)) AS max_ownership_pct,
                MAX(COALESCE(is_control, 0)) AS has_control,
                MAX(CASE WHEN COALESCE(is_control, 0) = 1 THEN ownership_pct ELSE 0 END) AS control_pct
            FROM active_ownership
            GROUP BY sub_code
        )
        SELECT
            c.code AS company_code,
            c.name AS company_name,
            COALESCE(c.parent_code, '') AS parent_code,
            COALESCE(parent.name, '') AS parent_name,
            COALESCE(c.level, 0) AS level,
            COALESCE(c.tree_path, '') AS tree_path,
            COALESCE(c.is_consolidated, 1) AS is_consolidated,
            COALESCE(d.business_group, '') AS business_group,
            COALESCE(d.business_type, '') AS business_type,
            COALESCE(d.region, '') AS region,
            COALESCE(d.is_operational, 1) AS is_operational,
            COALESCE(o.investor_codes, '') AS investor_codes,
            COALESCE(o.max_ownership_pct, 0) AS ownership_pct,
            COALESCE(o.has_control, 0) AS has_control,
            COALESCE(o.control_pct, 0) AS control_pct
        FROM companies c
        LEFT JOIN companies parent ON parent.code = c.parent_code
        LEFT JOIN dim_company d ON d.company_id = c.code
        LEFT JOIN ownership_summary o ON o.sub_code = c.code
        WHERE c.status = 1
          AND c.code <> 'ROOT'
        ORDER BY c.tree_path, c.code
    """)

    if len(df) == 0:
        return pd.DataFrame(columns=[
            "management_category",
            "display_module",
            "company_code",
            "company_name",
            "parent_code",
            "parent_name",
            "level",
            "ownership_pct",
            "investment_category",
            "business_group",
            "business_type",
            "region",
            "is_operational",
            "tree_path",
            "display_name",
        ])

    df["investment_category"] = df.apply(
        lambda row: classify_investment(row["ownership_pct"], row["has_control"]),
        axis=1,
    )
    df["management_category"] = df.apply(_management_category, axis=1)
    df["display_module"] = df.apply(_display_module, axis=1)
    df["display_name"] = df.apply(_display_name, axis=1)
    df["module_order"] = df["display_module"].map(_module_order).fillna(999).astype(int)
    df["category_order"] = df["management_category"].map({
        MANAGED_CATEGORY: 1,
        EXTERNAL_CATEGORY: 2,
    }).fillna(9).astype(int)
    df["is_operational"] = df["is_operational"].astype(int).map({1: "是", 0: "否"}).fillna("是")
    df["is_consolidated"] = df["is_consolidated"].astype(int).map({1: "是", 0: "否"}).fillna("是")
    return df.sort_values(["category_order", "module_order", "tree_path", "company_code"]).reset_index(drop=True)


def _management_category(row: pd.Series) -> str:
    ownership_pct = float(row.get("ownership_pct") or 0)
    has_control = int(row.get("has_control") or 0)
    is_operational = int(row.get("is_operational") or 0)
    business_group = normalize_business_group(row.get("business_group"))

    if business_group == "外部投资模块":
        return EXTERNAL_CATEGORY
    if ownership_pct > 0 and has_control == 0:
        return EXTERNAL_CATEGORY
    if is_operational == 0 and ownership_pct > 0 and has_control == 0:
        return EXTERNAL_CATEGORY
    return MANAGED_CATEGORY


def _display_module(row: pd.Series) -> str:
    if _management_category(row) == EXTERNAL_CATEGORY:
        return EXTERNAL_MODULE

    business_group = normalize_business_group(row.get("business_group"))
    if business_group in MANAGED_MODULES:
        return business_group

    text = " ".join([
        str(row.get("company_code") or ""),
        str(row.get("company_name") or ""),
        str(row.get("business_group") or ""),
        str(row.get("business_type") or ""),
    ])
    if "托育" in text:
        return "托育模块"
    if "少年宫" in text:
        return "少年宫模块"
    if any(token in text for token in ["书城", "书店"]):
        return "尔遇书城模块"
    if any(token in text for token in ["尔遇书馆", "书馆"]):
        return "尔遇书馆模块"
    if "幼儿" in text:
        return "幼儿园模块"
    if any(token in text for token in ["文旅", "探幽"]):
        return "文旅模块"
    if "国际" in text or str(row.get("company_code") or "").startswith("10102"):
        return "国际教育模块"
    if any(token in text for token in ["非学科", "素质", "虎翼营", "拔创", "校区"]):
        return "非学科素质中心模块"
    if "多维学校" in text:
        return "学校模块"
    if "物业" in text:
        return "物业公司"
    if any(token in text for token in ["集团", "管理中心", "科技", "职能"]):
        return "职能公司模块"
    return FALLBACK_MANAGED_MODULE


def _display_name(row: pd.Series) -> str:
    level = max(int(row.get("level") or 0) - 1, 0)
    prefix = "  " * level
    return f"{prefix}- {row.get('company_code')} {row.get('company_name')}"


def _module_order(module: str) -> int:
    if module in MANAGED_MODULES:
        return MANAGED_MODULES.index(module) + 1
    if module == FALLBACK_MANAGED_MODULE:
        return len(MANAGED_MODULES) + 1
    if module == EXTERNAL_MODULE:
        return 1
    return 999
