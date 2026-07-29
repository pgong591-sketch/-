"""
财务数据仓库 - Streamlit Web 界面 (精美版)
提供上传、查询、导出等功能的可视化界面。
启动方式：streamlit run app.py
"""

import os, sys, tempfile, io, zipfile
import re
from pathlib import Path
from html import escape
from math import ceil
from numbers import Number
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.db_connection import init_database, execute_sql, get_session, get_db_path
from sqlalchemy import text

from src.reports import (
    import_excel_to_db, precheck_import, get_companies, get_company, get_account_balance,
    get_balance_sheet, get_income_statement, get_cashflow,
    get_consolidated_balance_sheet, get_consolidated_income_statement,
    get_multi_period_summary, get_pl_detail, get_revenue_volume,
    get_non_subject_allocation, get_mgmt_dept_income_cost, get_non_subject_teaching_fee,
)
from src.models import REPORT_TYPES_CN
from src.excel_exporter import (
    export_to_excel,
    export_balance_sheet,
    export_income_statement,
    export_income_statement_pivot,
    export_cashflow,
    export_account_balance,
)
from src.company_hierarchy import (
    get_company_tree, rebuild_tree_path, get_subtree, get_summary_report,
    import_companies_from_excel, get_company_info, get_company_list_for_summary,
)
from src.company_dimension import (
    BUSINESS_GROUP_OPTIONS, BUSINESS_TYPE_OPTIONS, OPERATIONAL_OPTIONS,
    REGION_OPTIONS, get_company_dimensions, save_company_dimensions,
)
from src.ownership import CONTROL_OPTIONS, get_ownership_grid, save_ownership_grid
from src.company_structure import (
    EXTERNAL_CATEGORY, FALLBACK_MANAGED_MODULE, MANAGED_CATEGORY,
    MANAGED_MODULES, get_company_structure_view,
)
from src.dashboard_metrics import (
    COST_ITEMS,
    INCOME_ITEM,
    NET_PROFIT_ITEM,
    PL_COST_TOTAL_ITEM,
    PL_NET_PROFIT_ITEM,
    PL_REVENUE_ITEM,
    get_dashboard_periods,
    get_home_dashboard,
    preferred_pl_detail_rows,
)
from src.multidim_reports import get_multidim_income_statement, get_operating_summary
from src.template_workbook import TemplateWorkbookError, load_template_sheet, load_template_sheet_frame, read_template_bytes
from src.monthly_collection import (
    ensure_monthly_collection_schema,
    get_collection_matrix,
    get_collection_missing,
    refresh_collection_status,
    seed_requirements_from_active_companies,
)
from src.operating_summary import (
    build_empty_operating_summary_rows,
    build_operating_summary_rows,
    get_operating_summary_periods,
    get_operating_summary_source_detail,
)
from src.account_standardization import (
    ensure_account_standardization_schema,
    find_unmapped_accounts,
    get_account_mappings,
    get_mapping_coverage,
    get_standard_accounts,
    suggest_account_mappings,
    upsert_account_mapping,
    upsert_standard_account,
)
from src.base_settings_service import (
    COMPANY_HIERARCHY_ROOT_CODE,
    build_company_hierarchy_graph_data,
    detect_company_hierarchy_issues,
    get_base_health_checks,
    get_base_settings_overview,
    get_budget_campus_mapping_records,
    get_budget_campus_name_mappings,
    get_budget_campus_special_statuses,
    get_default_expanded_company_codes,
    resolve_company_identity,
)
from src.shared_name_mapping import (
    SHARED_NAME_MAPPING_ENV,
    build_shared_name_mapping_snapshot,
    get_shared_name_mapping_path,
    publish_shared_name_mapping_snapshot,
)
from src.filter_options_service import (
    apply_internal_management_fee_elimination,
    get_consolidation_company_codes,
    get_report_company_scope,
    get_workspace_company_options,
)

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:
    px = None
    go = None

st.set_page_config(page_title="财务数据仓库", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

PAGE_CSS = """
<style>
    :root {
        --app-bg: #f5f6fa;
        --surface: #ffffff;
        --surface-soft: #f8fafc;
        --text: #122033;
        --muted: #64748b;
        --border: rgba(148, 163, 184, 0.38);
        --border-soft: rgba(148, 163, 184, 0.24);
        --accent: #0a84ff;
        --accent-hover: #0071e3;
        --accent-soft: rgba(10, 132, 255, 0.10);
        --ios-blue-soft: rgba(10, 132, 255, 0.12);
        --ios-fill: rgba(255, 255, 255, 0.82);
        --ios-fill-hover: rgba(255, 255, 255, 0.96);
        --ios-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
        --ios-card-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
        --table-head: #eef6ff;
        --table-band: #f8fbff;
        --success: #248a3d;
        --danger: #d92d20;
    }

    * {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
            "SF Pro Text", "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
        letter-spacing: 0 !important;
    }

    .stApp {
        background: var(--app-bg);
        color: var(--text);
    }

    html,
    body,
    [data-testid="stAppViewContainer"] {
        min-width: 1120px;
    }

    [data-testid="stAppViewContainer"] > .main {
        min-height: 100vh;
    }

    .main > .block-container {
        padding: 0.95rem 2rem 2rem !important;
        max-width: none;
        width: 100% !important;
        min-height: calc(100vh - 1rem);
    }

    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewBlockContainer"] {
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: none !important;
        width: 100% !important;
    }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
    header[data-testid="stHeader"] {
        background: transparent;
        box-shadow: none;
    }
    div[data-testid="stDecoration"] { display: none; }
    section[data-testid="stSidebar"] button[kind="headerNoPadding"] {
        display: none !important;
    }

    [data-testid="collapsedControl"] {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }

    section[data-testid="stSidebar"] {
        background: var(--surface-soft);
        border-right: 1px solid var(--border-soft);
        width: 12.6rem !important;
        min-width: 12.6rem !important;
        max-width: 12.6rem !important;
    }

    section[data-testid="stSidebar"] > div {
        padding: 1rem 0.85rem 1.4rem;
    }

    section[data-testid="stSidebar"] hr {
        border: none;
        border-top: 1px solid var(--border-soft);
        margin: 1rem 0;
    }

    .sidebar-brand {
        padding: 0.1rem 0.25rem 0.7rem;
    }

    .app-title {
        font-size: 1.18rem;
        line-height: 1.25;
        font-weight: 700;
        color: var(--text);
        text-align: left;
        padding: 0;
    }

    .app-subtitle {
        font-size: 0.78rem;
        line-height: 1.4;
        color: var(--muted);
        text-align: left;
        padding-top: 0.25rem;
    }

    .nav-section-title {
        color: #86868b;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        margin: 0.85rem 0 0.28rem;
        padding: 0 0.35rem;
    }

    .nav-module-caption {
        color: var(--muted);
        font-size: 0.72rem;
        font-weight: 650;
        margin: 0.15rem 0 0.5rem;
        padding: 0 0.35rem;
    }

    .nav-current-module {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin: 0.35rem 0 0.7rem;
        padding: 0.65rem 0.75rem;
        border-radius: 8px;
        background: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%);
        border: 1px solid #dbeafe;
        color: #1e3a8a;
        font-size: 0.86rem;
        font-weight: 700;
    }

    .nav-current-module span:last-child {
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 650;
    }

    [class*="st-key-nav_module_pills"] div[role="radiogroup"] {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.36rem !important;
        width: 100%;
    }

    [class*="st-key-nav_module_pills"] [data-testid^="stBaseButton"] {
        border-radius: 8px !important;
        border: 1px solid var(--border-soft) !important;
        background: #ffffff !important;
        color: #475569 !important;
        min-height: 2.12rem !important;
        padding: 0.15rem 0.45rem !important;
        justify-content: center !important;
    }

    [class*="st-key-nav_module_pills"] [data-testid^="stBaseButton"] p {
        font-size: 0.78rem !important;
        font-weight: 650 !important;
        text-align: center !important;
        white-space: nowrap !important;
    }

    [class*="st-key-nav_module_pills"] [kind="pillsActive"] {
        background: #e8f2ff !important;
        border-color: #b9dcff !important;
        color: #005bb5 !important;
    }

    section[data-testid="stSidebar"] div.stButton {
        margin-bottom: 0.2rem;
    }

    section[data-testid="stSidebar"] div.stButton > button {
        width: 100%;
        justify-content: flex-start;
        min-height: 2.18rem;
        padding: 0.38rem 0.68rem;
        border-radius: 8px;
        border: 1px solid transparent;
        background: transparent;
        color: #424245;
        box-shadow: none;
        font-size: 0.92rem;
        font-weight: 500;
    }

    section[data-testid="stSidebar"] div.stButton > button p {
        width: 100%;
        text-align: left;
    }

    section[data-testid="stSidebar"] div.stButton > button > div,
    section[data-testid="stSidebar"] div.stButton > button span,
    section[data-testid="stSidebar"] div.stButton > button [data-testid="stMarkdownContainer"] {
        width: 100%;
        text-align: left;
    }

    section[data-testid="stSidebar"] div.stButton > button:hover {
        background: #f0f0f2;
        border-color: transparent;
        color: var(--text);
    }

    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        background: #e8f2ff;
        border-color: #cfe4ff;
        color: #005bb5;
        font-weight: 650;
        box-shadow: none;
    }

    .sidebar-note {
        margin-top: 1rem;
        padding: 0.75rem;
        border-radius: 8px;
        border: 1px solid var(--border-soft);
        color: var(--muted);
        background: #ffffff;
        font-size: 0.78rem;
        line-height: 1.45;
    }

    .page-header {
        font-size: 1.5rem;
        line-height: 1.25;
        font-weight: 720;
        color: var(--text);
        padding: 0.15rem 0 0.75rem;
        border-bottom: 1px solid var(--border-soft);
        margin-bottom: 1rem;
    }

    .card {
        background: var(--surface);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: var(--ios-card-shadow);
        border: 1px solid var(--border-soft);
    }

    .home-filter-card {
        background: #ffffff;
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 12px;
        padding: 0.7rem 0.78rem 0.58rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
    }

    [class*="_filter_card"][data-testid="stVerticalBlockBorderWrapper"],
    [class*="_filter_card"] [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(148, 163, 184, 0.24);
        border-radius: 12px;
        padding: 0.95rem 1rem 0.9rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
        backdrop-filter: blur(14px);
    }

    [class*="_filter_card"][data-testid="stVerticalBlock"],
    [class*="_filter_card"] [data-testid="stVerticalBlock"] {
        gap: 0.48rem;
    }

    [class*="_filter_card"] label,
    [class*="_filter_card"] [data-testid="stWidgetLabel"] p {
        color: #475569 !important;
        font-size: 0.78rem !important;
        font-weight: 650 !important;
    }

    [class*="_filter_card"] div[data-baseweb="select"] > div,
    [class*="_filter_card"] div[data-baseweb="input"] > div {
        min-height: 2.36rem !important;
        border-radius: 10px !important;
        background: rgba(255, 255, 255, 0.94) !important;
        border-color: rgba(148, 163, 184, 0.28) !important;
    }

    .workspace-filter-summary {
        color: #5b6b82;
        font-size: 0.76rem;
        font-weight: 650;
        margin-top: -0.18rem;
        margin-bottom: 0;
    }

    [class*="_period_quick_pills"] div[role="radiogroup"],
    [class*="_range_quick_pills"] div[role="radiogroup"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        gap: 0.35rem !important;
        overflow-x: auto !important;
        padding-bottom: 0.1rem;
    }

    [class*="_period_quick_pills"] [data-testid^="stBaseButton"],
    [class*="_range_quick_pills"] [data-testid^="stBaseButton"] {
        border-radius: 8px !important;
        min-height: 2.02rem !important;
        padding: 0.1rem 0.62rem !important;
        border: 1px solid #d9e2ef !important;
        background: #ffffff !important;
        color: #334155 !important;
        flex: 0 0 auto !important;
    }

    [class*="_period_quick_pills"] [kind="pillsActive"],
    [class*="_range_quick_pills"] [kind="pillsActive"] {
        background: #eaf2ff !important;
        border-color: #0f5fd6 !important;
        color: #0f5fd6 !important;
        font-weight: 750 !important;
    }

    .home-filter-title {
        font-size: 0.9rem;
        color: #17345f;
        font-weight: 740;
        margin-bottom: 0.05rem;
        display: flex;
        align-items: center;
        gap: 0.45rem;
    }

    .home-filter-title::before {
        content: "";
        width: 0.2rem;
        height: 0.86rem;
        border-radius: 999px;
        background: var(--accent);
    }

    .home-filter-divider {
        border-top: 1px solid var(--border-soft);
        margin: 0.65rem 0 0.55rem;
    }

    .home-filter-note {
        color: var(--muted);
        font-size: 0.78rem;
        margin-top: 0.35rem;
    }

    .quick-filter-label {
        color: #64748b;
        font-size: 0.76rem;
        font-weight: 650;
        padding-top: 0.38rem;
        white-space: nowrap;
        display: inline-block;
        min-width: 3.05rem;
    }

    [class*="_filter_year_pills"],
    [class*="_filter_month_pills"],
    [class*="_filter_group_pills"] {
        margin-left: 0 !important;
        padding-left: 0.12rem !important;
    }

    [class*="_filter_year_pills"] [data-testid^="stBaseButton"] p,
    [class*="_filter_month_pills"] [data-testid^="stBaseButton"] p {
        font-size: 0.76rem !important;
        font-weight: 560 !important;
        white-space: nowrap !important;
    }

    [class*="_filter_group_pills"] [data-testid^="stBaseButton"] p {
        font-size: 0.8rem !important;
        font-weight: 580 !important;
        white-space: nowrap !important;
    }

    [class*="_filter_year_pills"] [data-testid^="stBaseButton"],
    [class*="_filter_month_pills"] [data-testid^="stBaseButton"],
    [class*="_filter_group_pills"] [data-testid^="stBaseButton"] {
        border-radius: 999px !important;
        border: 1px solid rgba(148, 163, 184, 0.28) !important;
        background: rgba(255, 255, 255, 0.9) !important;
        color: #334155 !important;
        min-height: 2.06rem !important;
        padding: 0.1rem 0.78rem !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03) !important;
    }

    [class*="_filter_year_pills"] [kind="pillsActive"],
    [class*="_filter_month_pills"] [kind="pillsActive"],
    [class*="_filter_group_pills"] [kind="pillsActive"] {
        background: rgba(10, 132, 255, 0.13) !important;
        border-color: rgba(10, 132, 255, 0.34) !important;
        color: #0066cc !important;
        box-shadow: inset 0 0 0 1px rgba(10, 132, 255, 0.08) !important;
    }

    [class*="_filter_year_pills"] div[role="radiogroup"],
    [class*="_filter_month_pills"] div[role="radiogroup"],
    [class*="_filter_group_pills"] div[role="radiogroup"] {
        display: flex !important;
        flex-wrap: wrap !important;
        overflow-x: visible !important;
        gap: 0.45rem !important;
        row-gap: 0.38rem !important;
        padding-bottom: 0.1rem;
    }

    [class*="_filter_group_pills"] [data-testid^="stBaseButton"] {
        flex: 0 0 auto !important;
    }

    .operating-filter-label {
        min-width: 4.65rem;
        text-align: right;
        padding-right: 0.28rem;
        box-sizing: border-box;
    }

    [class*="profit_original_filter_year_pills"],
    [class*="profit_original_filter_month_pills"],
    [class*="profit_original_filter_group_pills"],
    [class*="operating_summary_filter_year_pills"],
    [class*="operating_summary_filter_month_pills"],
    [class*="operating_summary_filter_group_pills"] {
        margin-left: 0 !important;
        padding-left: 0.38rem !important;
    }

    [class*="profit_original_filter_group_pills"] div[role="radiogroup"],
    [class*="operating_summary_filter_group_pills"] div[role="radiogroup"] {
        flex-wrap: wrap !important;
        overflow-x: visible !important;
        gap: 0.55rem !important;
        row-gap: 0.38rem !important;
    }

    [class*="_summary_mode_pills"] [data-testid^="stBaseButton"] {
        border-radius: 10px !important;
        border: 1px solid rgba(10, 132, 255, 0.24) !important;
        background: rgba(10, 132, 255, 0.08) !important;
        color: #0066cc !important;
        min-height: 2.22rem !important;
        padding: 0.12rem 0.75rem !important;
    }

    [class*="_summary_mode_pills"] [kind="pillsActive"] {
        background: rgba(10, 132, 255, 0.14) !important;
        border-color: rgba(10, 132, 255, 0.38) !important;
        color: #0057b8 !important;
    }

    [class*="_summary_mode_pills"] [data-testid^="stBaseButton"] p {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }

    [class*="_filter_apply"] button,
    [class*="_filter_reset"] button,
    [class*="_filter_toggle"] button {
        min-height: 2.36rem !important;
        border-radius: 10px !important;
        font-weight: 650 !important;
        padding: 0.12rem 0.62rem !important;
        font-size: 0.8rem !important;
        margin-top: 1.55rem !important;
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.04) !important;
    }

    [class*="_filter_apply"] button {
        background: #0a84ff !important;
        border-color: #0a84ff !important;
        color: #ffffff !important;
        box-shadow: 0 6px 14px rgba(10, 132, 255, 0.18) !important;
    }

    [class*="_filter_reset"] button,
    [class*="_filter_toggle"] button {
        background: rgba(255, 255, 255, 0.88) !important;
        border-color: rgba(148, 163, 184, 0.28) !important;
        color: #1f2a3d !important;
    }

    [class*="_filter_reset"] button:hover,
    [class*="_filter_toggle"] button:hover {
        background: rgba(10, 132, 255, 0.06) !important;
        border-color: rgba(10, 132, 255, 0.28) !important;
        color: #0b57cb !important;
    }

    [class*="_company_units"] [data-baseweb="select"] {
        min-height: 2.36rem !important;
    }

    [class*="_company_units"] [data-baseweb="tag"] {
        max-width: 12rem !important;
    }

    .metric-card {
        background: var(--surface);
        border-radius: 10px;
        padding: 1.15rem;
        text-align: left;
        border: 1px solid var(--border-soft);
        box-shadow: none;
    }

    .metric-card .icon {
        font-size: 1.22rem;
        margin-bottom: 0.45rem;
        opacity: 0.82;
    }

    .metric-card .value {
        font-size: 1.62rem;
        line-height: 1.15;
        font-weight: 720;
        color: var(--text);
    }

    .metric-card .label {
        font-size: 0.8rem;
        color: var(--muted);
        font-weight: 520;
        text-transform: none;
        margin-top: 0.2rem;
    }

    .success-box {
        padding: 0.75rem 1rem;
        background: #f0f9f2;
        border-radius: 8px;
        border-left: 3px solid var(--success);
        margin: 0.5rem 0;
        font-size: 0.9rem;
        color: var(--text);
    }

    .error-box {
        padding: 0.75rem 1rem;
        background: #fff4f2;
        border-radius: 8px;
        border-left: 3px solid var(--danger);
        margin: 0.5rem 0;
        font-size: 0.9rem;
        color: var(--text);
    }

    div.stButton > button {
        border-radius: 9px;
        font-weight: 620;
        font-size: 0.82rem;
        padding: 0.24rem 0.68rem;
        min-height: 2.08rem;
        border: 1px solid rgba(148, 163, 184, 0.35);
        background: var(--ios-fill);
        color: #1f2a3d;
        transition: background-color .12s ease, border-color .12s ease, color .12s ease !important;
        box-shadow: var(--ios-shadow);
    }

    div.stButton > button [class*="material-symbols"] {
        font-size: 1rem !important;
        font-weight: 300 !important;
        line-height: 1 !important;
        margin-right: 0.28rem !important;
        opacity: 0.82;
        font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 20;
    }

    div.stButton > button:hover {
        background: var(--ios-fill-hover);
        border-color: rgba(10, 132, 255, 0.32);
        color: #0b57cb;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 0.75rem;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.72rem;
    }

    div.stButton > button[kind="primary"] {
        background: var(--accent);
        border-color: var(--accent);
        color: #ffffff;
        box-shadow: none;
    }

    div.stButton > button[kind="primary"]:hover {
        background: var(--accent-hover);
        border-color: var(--accent-hover);
        color: #ffffff;
    }

    div[data-testid="stDownloadButton"] > button {
        border-radius: 9px;
        min-height: 2.08rem;
        padding: 0.24rem 0.68rem;
        border: 1px solid rgba(148, 163, 184, 0.35);
        background: var(--ios-fill);
        color: #1f2a3d;
        box-shadow: var(--ios-shadow);
        font-size: 0.82rem;
        font-weight: 620;
    }

    div[data-testid="stDownloadButton"] > button:hover {
        background: var(--ios-fill-hover);
        border-color: rgba(10, 132, 255, 0.32);
        color: #0b57cb;
    }

    div[data-testid="stDataFrame"],
    div[data-testid="stDataEditor"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid var(--border-soft);
        box-shadow: var(--ios-shadow);
        background: #ffffff;
    }

    div[data-testid="stDataFrame"] {
        min-height: 15rem;
    }

    div[data-testid="stDataFrame"] thead tr th {
        background: var(--table-head);
        color: #10233f;
        font-weight: 680;
        font-size: 0.8rem;
        padding: 0.55rem 0.75rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    }

    div[data-testid="stDataFrame"] tbody tr:nth-child(even) {
        background: var(--table-band);
    }

    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="columnheader"] {
        background: var(--table-head) !important;
        color: #10233f !important;
        font-weight: 680 !important;
        font-size: 0.8rem !important;
    }

    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataEditor"] [role="gridcell"] {
        font-size: 0.82rem !important;
        color: #122033 !important;
        font-variant-numeric: tabular-nums;
    }

    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stMultiSelect"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stFileUploader"] label,
    div[data-testid="stRadio"] label {
        color: #4b5f78 !important;
        font-size: 0.78rem !important;
        font-weight: 620 !important;
        margin-bottom: 0.12rem !important;
    }

    div[data-baseweb="select"] > div,
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {
        min-height: 2.28rem !important;
        border-radius: 9px !important;
        border-color: rgba(148, 163, 184, 0.34) !important;
        background: rgba(255, 255, 255, 0.9) !important;
        font-size: 0.86rem !important;
        color: #122033 !important;
        box-shadow: var(--ios-shadow) !important;
    }

    div[data-baseweb="select"] span,
    div[data-testid="stTextInput"] input::placeholder {
        font-size: 0.86rem !important;
        color: #8a95a8 !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.42rem;
        border-bottom: 1px solid var(--border-soft);
        background: rgba(255,255,255,0.62);
        border-radius: 10px 10px 0 0;
        padding: 0.18rem 0.2rem 0;
    }

    .stTabs [data-baseweb="tab"] {
        height: 2.18rem;
        padding: 0 0.72rem;
        border-radius: 9px 9px 0 0;
        color: #42526a;
        font-size: 0.82rem;
        font-weight: 620;
    }

    .stTabs [aria-selected="true"] {
        color: var(--accent) !important;
        background: rgba(10, 132, 255, 0.10) !important;
        border-bottom: 2px solid var(--accent) !important;
    }

    div[data-testid="stFileUploader"] {
        border-radius: 12px;
        border: 1px dashed rgba(10, 132, 255, 0.32);
        background: rgba(255,255,255,0.72);
        padding: 1rem;
    }

    div[data-testid="stFileUploader"]:hover {
        border-color: var(--accent);
        background: rgba(10,132,255,0.06);
    }

    div[data-testid="stProgress"] > div {
        background: var(--accent);
        border-radius: 8px;
    }

    .bi-hero {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.9fr);
        gap: 0.85rem;
        align-items: stretch;
        background: #123834;
        color: #ffffff;
        border-radius: 8px;
        padding: 1.05rem;
        border: 1px solid #0f2f2c;
        margin-bottom: 0.85rem;
    }

    .bi-eyebrow {
        font-size: 0.76rem;
        font-weight: 700;
        color: #9ee2d4;
        margin-bottom: 0.4rem;
    }

    .bi-title {
        font-size: 1.68rem;
        line-height: 1.15;
        font-weight: 780;
    }

    .bi-subtitle {
        color: #d8eee9;
        font-size: 0.9rem;
        line-height: 1.55;
        margin-top: 0.55rem;
    }

    .bi-hero-side {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.6rem;
    }

    .bi-hero-stat {
        background: rgba(255,255,255,.08);
        border: 1px solid rgba(255,255,255,.14);
        border-radius: 8px;
        padding: 0.75rem;
    }

    .bi-hero-stat .num {
        font-size: 1.15rem;
        font-weight: 760;
        line-height: 1.2;
    }

    .bi-hero-stat .txt {
        color: #c4ddd8;
        font-size: 0.74rem;
        margin-top: 0.28rem;
    }

    .bi-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.8rem 0;
    }

    .bi-kpi-card {
        background: #ffffff;
        border: 1px solid var(--border-soft);
        border-left: 4px solid #2b7de9;
        border-radius: 8px;
        padding: 0.62rem 0.78rem;
        min-height: 5.25rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
    }

    .bi-kpi-card.profit { border-left-color: #2d9d78; }
    .bi-kpi-card.cash { border-left-color: #d8912f; }
    .bi-kpi-card.risk { border-left-color: #d65045; }
    .bi-kpi-card.neutral { border-left-color: #6b7280; }
    .bi-kpi-card.selected {
        border-color: rgba(43, 125, 233, 0.42);
        border-left-color: var(--accent);
        box-shadow: 0 10px 24px rgba(43, 125, 233, 0.12);
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
    }

    .bi-kpi-label {
        color: var(--muted);
        font-size: 0.78rem;
        font-weight: 650;
        width: 100%;
    }

    .bi-kpi-value {
        color: var(--text);
        font-size: 1.42rem;
        line-height: 1.15;
        font-weight: 780;
        margin-top: 0.28rem;
        width: 100%;
    }

    .bi-kpi-value-link {
        color: inherit;
        text-decoration: none;
        border-bottom: 0;
        cursor: pointer;
        transition: color .15s ease, transform .15s ease;
        display: inline-block;
    }

    .bi-kpi-value-link:hover {
        color: var(--accent);
        transform: translateY(-1px);
    }

    .bi-kpi-card.selected .bi-kpi-value-link {
        color: var(--accent);
    }

    .bi-kpi-delta {
        color: #52606d;
        font-size: 0.76rem;
        margin-top: 0.32rem;
        width: 100%;
    }

    .bi-kpi-trends {
        display: flex;
        justify-content: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        color: #64748b;
        font-size: 0.72rem;
        margin-top: 0.28rem;
        width: 100%;
    }

    .bi-kpi-trend.good { color: #15803d; font-weight: 700; }
    .bi-kpi-trend.risk { color: #dc2626; font-weight: 700; }
    .bi-kpi-trend.neutral { color: #64748b; }

    .home-top-kpi-grid .bi-kpi-card {
        padding: 0.8rem 0.88rem;
        min-height: 6.15rem;
    }

    .home-top-kpi-grid .bi-kpi-label {
        font-size: 1.03rem;
        line-height: 1.22;
        font-weight: 680;
    }

    .home-top-kpi-grid .bi-kpi-value {
        font-size: 2rem;
        line-height: 1.08;
        font-weight: 700;
        margin-top: 0.34rem;
    }

    .home-top-kpi-grid .bi-kpi-delta {
        font-size: 0.98rem;
        line-height: 1.25;
        margin-top: 0.38rem;
    }

    .home-top-kpi-grid .bi-kpi-trends {
        font-size: 0.9rem;
        line-height: 1.22;
        margin-top: 0.34rem;
    }

    .home-drill-panel-title {
        color: var(--text);
        font-size: 1.02rem;
        font-weight: 760;
        margin: 0.05rem 0 0.18rem;
    }

    .home-drill-panel-note {
        color: var(--muted);
        font-size: 0.78rem;
        line-height: 1.5;
        margin-bottom: 0.35rem;
    }

    .home-detail-overlay {
        position: fixed;
        inset: 0;
        z-index: 1000000;
        background: rgba(15, 23, 42, 0.28);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.35rem;
    }

    .home-detail-layer {
        background: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(203, 213, 225, 0.85);
        border-radius: 24px;
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
        overflow: hidden;
        color: var(--text);
        display: flex;
        flex-direction: column;
    }

    .home-detail-modal {
        width: min(92vw, 1440px);
        height: min(88vh, 900px);
        max-height: calc(100vh - 0.7rem);
        margin: auto;
    }

    .home-detail-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.05rem 1.18rem 0.78rem;
        border-bottom: 1px solid #e2e8f0;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
    }

    .home-detail-title {
        font-size: 1.08rem;
        line-height: 1.25;
        font-weight: 780;
        color: #18314f;
    }

    .home-detail-subtitle {
        margin-top: 0.28rem;
        font-size: 0.82rem;
        line-height: 1.45;
        color: #64748b;
    }

    .home-detail-bridge-note {
        margin-top: 0.56rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.38rem 0.55rem;
        align-items: center;
        color: #475569;
        font-size: 0.78rem;
        line-height: 1.45;
    }

    .home-detail-bridge-note strong {
        color: #18314f;
        font-weight: 760;
    }

    .home-detail-bridge-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.18rem;
        border: 1px solid #dbe5f1;
        border-radius: 999px;
        padding: 0.12rem 0.48rem;
        background: #f8fbff;
        white-space: nowrap;
    }

    .home-detail-unit-note {
        margin: 0 0 0.55rem;
        color: #64748b;
        font-size: 0.8rem;
        line-height: 1.35;
        text-align: right;
    }

    .home-detail-close {
        flex: 0 0 auto;
        width: 2rem;
        height: 2rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        color: #475569;
        background: #eef3f8;
        font-size: 1.35rem;
        line-height: 1;
        font-weight: 500;
    }

    .home-detail-close:hover {
        color: #0f172a;
        background: #dbe8f5;
    }

    .home-detail-body {
        padding: 1rem 1.18rem 1.2rem;
        flex: 1 1 auto;
        min-height: 0;
        overflow: auto;
    }

    .home-detail-modal .home-detail-body {
        max-height: none;
    }

    .home-detail-table-wrap {
        width: 100%;
        overflow: auto;
        max-height: calc(88vh - 10.5rem);
        border: 1px solid #dbe5f1;
        border-radius: 12px;
        background: #ffffff;
    }

    .home-detail-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: 0.86rem;
        min-width: 100%;
    }

    .home-detail-table th,
    .home-detail-table td {
        border: 1px solid #dbe5f1;
        padding: 0.58rem 0.66rem;
        text-align: center;
        vertical-align: middle;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .home-detail-table th.col-company,
    .home-detail-table td.col-company {
        white-space: nowrap;
    }

    .home-detail-table th.col-text,
    .home-detail-table td.col-text {
        white-space: nowrap;
    }

    .home-detail-table th {
        position: sticky;
        top: 0;
        z-index: 4;
        background: #eaf3ff;
        color: #18314f;
        font-weight: 760;
    }

    .home-detail-table th:first-child {
        left: 0;
        z-index: 7;
        box-shadow: 2px 0 0 rgba(148, 163, 184, 0.24);
    }

    .home-detail-table td:first-child {
        position: sticky;
        left: 0;
        z-index: 3;
        background: #ffffff;
        box-shadow: 2px 0 0 rgba(148, 163, 184, 0.18);
    }

    .home-detail-table tbody tr:nth-child(even) td:first-child {
        background: #fbfdff;
    }

    .home-detail-sort-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.28rem;
        color: inherit;
        text-decoration: none;
        width: 100%;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .home-detail-sort-label {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .home-detail-sort {
        color: #64748b;
        font-size: 0.72rem;
        line-height: 1;
    }

    .home-detail-sort.active {
        color: #2563eb;
    }

    .home-detail-back {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        margin-bottom: 0.32rem;
        color: #2563eb;
        font-size: 0.82rem;
        font-weight: 760;
        text-decoration: none;
    }

    .home-detail-row-link {
        color: #1d4ed8;
        font-weight: 820;
        text-decoration: none;
        border-bottom: 1px solid rgba(29, 78, 216, 0.35);
    }

    .home-detail-row-link:hover {
        color: #1e40af;
        border-bottom-color: rgba(30, 64, 175, 0.75);
    }

    .home-detail-table td.num {
        text-align: right;
        font-variant-numeric: tabular-nums;
    }

    .home-detail-table td.neg {
        color: #dc2626;
        font-weight: 760;
        background: #fff5f5;
    }

    .home-detail-table td.pos {
        color: #15803d;
        font-weight: 760;
    }

    .home-detail-tag-risk,
    .home-detail-tag-warn,
    .home-detail-tag-good {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 3rem;
        padding: 0.14rem 0.48rem;
        border-radius: 999px;
        font-weight: 760;
    }

    .home-detail-tag-risk { color: #b42318; background: #fee4e2; }
    .home-detail-tag-warn { color: #b54708; background: #fff4d6; }
    .home-detail-tag-good { color: #027a48; background: #dcfae6; }

    .home-detail-empty {
        padding: 1rem;
        border: 1px dashed #cbd5e1;
        border-radius: 12px;
        color: #64748b;
        background: #f8fafc;
        text-align: center;
    }

    .operating-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.78rem;
        margin: 0.8rem 0 0.85rem;
    }

    .operating-kpi-card {
        background: #ffffff;
        border: 1px solid #dfe8f5;
        border-radius: 8px;
        padding: 0.88rem 0.95rem 0.55rem;
        min-height: 8.7rem;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
        overflow: hidden;
    }

    .operating-kpi-title {
        color: #17345f;
        font-size: 0.86rem;
        font-weight: 750;
        line-height: 1.25;
    }

    .operating-kpi-value {
        color: #0b172a;
        font-size: 1.6rem;
        line-height: 1.08;
        font-weight: 780;
        margin-top: 0.48rem;
        font-variant-numeric: tabular-nums;
    }

    .operating-kpi-delta {
        color: #53627a;
        font-size: 0.8rem;
        margin-top: 0.42rem;
    }

    .operating-kpi-delta .up { color: #ff3b30; font-weight: 720; }
    .operating-kpi-delta .down { color: #16a34a; font-weight: 720; }
    .operating-kpi-delta .flat { color: #64748b; font-weight: 720; }

    .operating-sparkline {
        width: 100%;
        height: 2.35rem;
        margin-top: 0.48rem;
        display: block;
    }

    .operating-board {
        display: grid;
        grid-template-columns: 1.08fr 1.38fr 1.02fr 0.92fr;
        gap: 0.78rem;
        margin: 0.85rem 0;
    }

    .operating-panel {
        background: #ffffff;
        border: 1px solid #dfe8f5;
        border-radius: 8px;
        padding: 0.88rem 0.95rem;
        min-height: 18rem;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
    }

    .operating-panel-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.6rem;
        color: #17345f;
        font-size: 0.92rem;
        font-weight: 760;
        margin-bottom: 0.72rem;
    }

    .operating-panel-title span:last-child {
        color: #2563eb;
        font-size: 0.76rem;
        font-weight: 650;
    }

    .operating-alert-list {
        display: grid;
        gap: 0.58rem;
    }

    .operating-alert-item {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 0.52rem;
        align-items: start;
        border-bottom: 1px solid #edf2f8;
        padding-bottom: 0.54rem;
        color: #344256;
        font-size: 0.78rem;
        line-height: 1.42;
    }

    .operating-alert-tag {
        border: 1px solid #fed7aa;
        background: #fff7ed;
        color: #ea580c;
        border-radius: 4px;
        padding: 0.1rem 0.26rem;
        font-size: 0.72rem;
        font-weight: 750;
        white-space: nowrap;
    }

    .operating-alert-tag.down {
        border-color: #bbf7d0;
        background: #f0fdf4;
        color: #16a34a;
    }

    .operating-empty {
        color: #64748b;
        font-size: 0.8rem;
        padding: 1.8rem 0;
        text-align: center;
    }

    .operating-detail-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        background: #ffffff;
        border: 1px solid #dfe8f5;
        border-radius: 8px;
        padding: 0.72rem 0.86rem;
        margin: 0.8rem 0 0.55rem;
    }

    .operating-detail-title {
        color: #17345f;
        font-size: 0.94rem;
        font-weight: 760;
    }

    .operating-detail-subtitle {
        color: #64748b;
        font-size: 0.76rem;
        margin-top: 0.18rem;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0B2342 0%, #081B33 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.10) !important;
        width: 12.6rem !important;
        min-width: 12.6rem !important;
        max-width: 12.6rem !important;
    }

    section[data-testid="stSidebar"] > div {
        padding: 0.7rem 0.68rem 1rem !important;
    }

    section[data-testid="stSidebar"] hr {
        border-top: 1px solid rgba(255,255,255,0.16) !important;
        margin: 0.62rem 0 0.72rem !important;
    }

    .sidebar-brand {
        padding: 0.08rem 0.16rem 0.45rem !important;
    }

    .app-title {
        color: #f8fafc !important;
        font-size: 1.36rem !important;
        line-height: 1.18 !important;
        font-weight: 780 !important;
        text-align: left !important;
    }

    .app-subtitle {
        color: #b6c2d6 !important;
        font-size: 0.82rem !important;
        line-height: 1.25 !important;
        padding-top: 0.28rem !important;
        text-align: left !important;
    }

    .nav-section-title {
        color: #94a3b8 !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.02em !important;
        text-transform: none !important;
        margin: 0.82rem 0 0.34rem !important;
        padding: 0 0.25rem 0 1.15rem !important;
        text-align: left !important;
    }

    .nav-section-title::before {
        content: "";
        display: inline-block;
        width: 0.28rem;
        height: 0.28rem;
        margin-right: 0.42rem;
        border-radius: 999px;
        background: rgba(96,165,250,0.75);
        vertical-align: 0.08rem;
    }

    section[data-testid="stSidebar"] div.stButton {
        margin-bottom: 0.18rem !important;
    }

    section[data-testid="stSidebar"] div.stButton > button {
        position: relative !important;
        width: 100% !important;
        min-height: 1.92rem !important;
        padding: 0.22rem 0.52rem !important;
        border-radius: 7px !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        box-shadow: none !important;
        color: #cbd5e1 !important;
        font-size: 0.82rem !important;
        font-weight: 520 !important;
        justify-content: flex-start !important;
        overflow: hidden !important;
    }

    section[data-testid="stSidebar"] div.stButton > button:hover {
        background: rgba(255,255,255,0.06) !important;
        border-color: transparent !important;
        color: #f8fafc !important;
    }

    section[data-testid="stSidebar"] div.stButton > button p,
    section[data-testid="stSidebar"] div.stButton > button > div,
    section[data-testid="stSidebar"] div.stButton > button span,
    section[data-testid="stSidebar"] div.stButton > button [data-testid="stMarkdownContainer"] {
        width: 100% !important;
        text-align: left !important;
    }

    [class*="st-key-nav_module_toggle_"] button {
        min-height: 3.42rem !important;
        margin-top: 0.6rem !important;
        padding: 0.52rem 0.64rem !important;
        color: #e5eaf3 !important;
        font-size: 1rem !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,0.05) !important;
        border-color: rgba(255,255,255,0.08) !important;
        letter-spacing: 0 !important;
    }

    [class*="st-key-nav_module_toggle_"] button:hover {
        background: rgba(255,255,255,0.08) !important;
        color: #ffffff !important;
    }

    [class*="st-key-nav_module_toggle_"] button p {
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        gap: 0.5rem !important;
        width: 100% !important;
        white-space: nowrap !important;
        font-size: 1rem !important;
        font-weight: 800 !important;
    }

    [class*="st-key-nav_module_toggle_"] button[kind="primary"] {
        background: rgba(37,99,235,0.14) !important;
        border-color: rgba(96,165,250,0.28) !important;
        color: #f8fafc !important;
    }

    [class*="st-key-nav_module_toggle_"] button[kind="primary"]::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0.42rem;
        bottom: 0.42rem;
        width: 3px;
        border-radius: 999px;
        background: #60a5fa;
        opacity: 0.8;
    }

    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button {
        min-height: 2.15rem !important;
        margin: 0.12rem 0 0.12rem 0.82rem !important;
        padding: 0.28rem 0.52rem 0.28rem 0.78rem !important;
        color: #cbd5e1 !important;
        font-size: 0.92rem !important;
        font-weight: 680 !important;
        border-radius: 9px !important;
    }

    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button[kind="primary"] {
        background: rgba(59,130,246,0.18) !important;
        border-color: transparent !important;
        color: #bfdbfe !important;
        font-weight: 740 !important;
    }

    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button[kind="primary"]::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0.36rem;
        bottom: 0.36rem;
        width: 3px;
        border-radius: 999px;
        background: #60a5fa;
    }

    .sidebar-note {
        margin-top: 0.9rem !important;
        padding: 0.62rem 0.7rem !important;
        background: rgba(255,255,255,0.06) !important;
        border-color: rgba(255,255,255,0.12) !important;
        color: rgba(203,213,225,0.78) !important;
        font-size: 0.74rem !important;
        line-height: 1.35 !important;
    }

    .sidebar-font-control-title {
        color: #e5eaf3 !important;
        font-size: 0.82rem !important;
        line-height: 1.25 !important;
        font-weight: 760 !important;
        margin: 0.78rem 0 0.42rem !important;
        padding: 0 0.25rem !important;
    }

    [class*="st-key-ui_font_size_mode"] {
        margin: 0 0 0.56rem !important;
        padding: 0.48rem 0.5rem !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255,255,255,0.10) !important;
        background: rgba(255,255,255,0.05) !important;
    }

    [class*="st-key-ui_font_size_mode"] div[role="radiogroup"] {
        display: grid !important;
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 0.25rem !important;
        width: 100% !important;
    }

    [class*="st-key-ui_font_size_mode"] label {
        min-height: 2rem !important;
        margin: 0 !important;
        padding: 0.16rem 0.24rem !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255,255,255,0.10) !important;
        background: rgba(15, 23, 42, 0.18) !important;
        color: #d7e3f1 !important;
        justify-content: center !important;
    }

    [class*="st-key-ui_font_size_mode"] label,
    [class*="st-key-ui_font_size_mode"] label span,
    [class*="st-key-ui_font_size_mode"] label div,
    [class*="st-key-ui_font_size_mode"] label p {
        color: #d7e3f1 !important;
    }

    [class*="st-key-ui_font_size_mode"] label:hover {
        background: rgba(59,130,246,0.20) !important;
        border-color: rgba(147,197,253,0.50) !important;
        color: #ffffff !important;
    }

    [class*="st-key-ui_font_size_mode"] label:hover,
    [class*="st-key-ui_font_size_mode"] label:hover span,
    [class*="st-key-ui_font_size_mode"] label:hover div,
    [class*="st-key-ui_font_size_mode"] label:hover p {
        color: #ffffff !important;
    }

    [class*="st-key-ui_font_size_mode"] label:has(input:checked) {
        background: #2563eb !important;
        border-color: #60a5fa !important;
        color: #ffffff !important;
        box-shadow: 0 0 0 1px rgba(147,197,253,0.24) inset !important;
    }

    [class*="st-key-ui_font_size_mode"] label:has(input:checked),
    [class*="st-key-ui_font_size_mode"] label:has(input:checked) span,
    [class*="st-key-ui_font_size_mode"] label:has(input:checked) div,
    [class*="st-key-ui_font_size_mode"] label:has(input:checked) p {
        color: #ffffff !important;
    }

    [class*="st-key-ui_font_size_mode"] label:has(input:focus-visible) {
        outline: 2px solid #93c5fd !important;
        outline-offset: 2px !important;
    }

    [class*="st-key-ui_font_size_mode"] label [data-testid="stMarkdownContainer"] p {
        font-size: 0.76rem !important;
        line-height: 1.2 !important;
        font-weight: 720 !important;
        text-align: center !important;
        white-space: nowrap !important;
        overflow: visible !important;
    }

    .bi-section-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.8rem 0;
    }

    .home-card-group-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        align-items: start;
    }

    .home-card-group-grid > .home-card-group-company-profit-rank {
        grid-column: 1 / -1;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .bi-panel {
        padding: 1.05rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .bi-panel-title {
        font-size: 1.32rem;
        line-height: 1.22;
        font-weight: 780;
        margin-bottom: 0.7rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .bi-panel-subtitle {
        font-size: 0.98rem;
        line-height: 1.4;
        margin-bottom: 0.9rem;
    }

    .bi-two-col {
        display: grid;
        grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
        gap: 0.75rem;
        margin: 0.8rem 0;
    }

    .bi-panel {
        background: #ffffff;
        border: 1px solid var(--border-soft);
        border-radius: 8px;
        padding: 0.88rem;
        min-height: 100%;
    }

    .home-card-group-link {
        display: block;
        color: inherit;
        text-decoration: none;
        height: 100%;
    }

    .home-card-group-link .bi-panel {
        transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
    }

    .home-card-group-link:hover .bi-panel,
    .home-card-group-link.active .bi-panel {
        border-color: rgba(37, 99, 235, 0.38);
        box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
        transform: translateY(-1px);
    }

    .bi-panel-title {
        font-size: 1rem;
        line-height: 1.25;
        font-weight: 750;
        color: var(--text);
        margin-bottom: 0.75rem;
    }

    .bi-panel-subtitle {
        color: var(--muted);
        font-size: 0.78rem;
        margin-top: -0.35rem;
        margin-bottom: 0.75rem;
    }

    .bi-progress-row {
        margin: 0.65rem 0 0.95rem;
    }

    .bi-progress-top {
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        color: #3f3f46;
        font-size: 0.82rem;
        font-weight: 650;
        margin-bottom: 0.35rem;
    }

    .bi-progress-track {
        width: 100%;
        height: 0.55rem;
        background: #eef2f3;
        border-radius: 999px;
        overflow: hidden;
    }

    .bi-progress-fill {
        height: 100%;
        border-radius: 999px;
        background: #2b7de9;
    }

    .bi-progress-fill.good { background: #2d9d78; }
    .bi-progress-fill.warn { background: #d8912f; }
    .bi-progress-fill.risk { background: #d65045; }

    .bi-micro {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
    }

    .bi-micro-row {
        border-top: 1px solid var(--border-soft);
        padding-top: 0.65rem;
    }

    .bi-micro-row .label {
        color: var(--muted);
        font-size: 0.75rem;
    }

    .bi-micro-row .value {
        color: var(--text);
        font-size: 1rem;
        font-weight: 720;
        margin-top: 0.15rem;
    }

    .bi-bar-row {
        display: grid;
        grid-template-columns: minmax(96px, 0.75fr) minmax(120px, 1.4fr) minmax(80px, 0.55fr);
        gap: 0.6rem;
        align-items: center;
        margin: 0.52rem 0;
        font-size: 0.78rem;
    }

    .bi-bar-name {
        color: #3f3f46;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .bi-bar-track {
        height: 0.58rem;
        background: #eef2f3;
        border-radius: 999px;
        overflow: hidden;
    }

    .bi-bar-fill {
        height: 100%;
        border-radius: 999px;
        background: #2b7de9;
    }

    .bi-bar-fill.positive { background: #2d9d78; }
    .bi-bar-fill.negative { background: #d65045; }
    .bi-bar-value {
        text-align: right;
        color: #52525b;
        font-weight: 650;
        white-space: nowrap;
    }

    .home-card-mini {
        display: grid;
        gap: 0.62rem;
    }

    .home-card-mini-row {
        display: grid;
        grid-template-columns: minmax(76px, 0.55fr) minmax(120px, 1fr) minmax(70px, 0.42fr);
        align-items: center;
        gap: 0.55rem;
        font-size: 0.78rem;
    }

    .home-card-mini-label {
        color: #3f3f46;
        font-weight: 680;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .home-card-mini-track {
        height: 0.56rem;
        position: relative;
        overflow: hidden;
        border-radius: 999px;
        background: #eef2f3;
    }

    .home-card-mini-track.benchmark::after {
        content: "";
        position: absolute;
        top: -2px;
        bottom: -2px;
        left: var(--benchmark-left, 0%);
        width: 2px;
        border-radius: 999px;
        background: #0f172a;
        opacity: 0.42;
    }

    .home-card-mini-fill {
        display: block;
        height: 100%;
        width: var(--fill-width, 0%);
        border-radius: 999px;
        background: #2b7de9;
    }

    .home-card-mini-fill.good { background: #2d9d78; }
    .home-card-mini-fill.warn { background: #d8912f; }
    .home-card-mini-fill.risk { background: #d65045; }

    .home-card-mini-value {
        text-align: right;
        color: #0f172a;
        font-weight: 760;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .home-card-note-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.45rem;
        margin-top: 0.72rem;
    }

    .home-card-note {
        border-top: 1px solid var(--border-soft);
        padding-top: 0.52rem;
        color: #64748b;
        font-size: 0.75rem;
        line-height: 1.35;
    }

    .home-card-note strong {
        display: block;
        color: #18314f;
        font-size: 0.9rem;
        margin-top: 0.1rem;
    }

    .home-card-note strong.good { color: #15803d; }
    .home-card-note strong.risk { color: #dc2626; }

    .home-funds-assurance {
        margin-top: 0.95rem;
        padding-top: 0.8rem;
        border-top: 1px solid var(--border-soft);
        display: grid;
        gap: 0.62rem;
    }

    .home-funds-assurance-head {
        color: #18314f;
        font-size: 1.14rem;
        line-height: 1.25;
        font-weight: 780;
    }

    .home-funds-assurance-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0;
        border-top: 1px solid #e5e7eb;
        border-left: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
        background: #ffffff;
    }

    .home-funds-assurance-item {
        min-width: 0;
        padding: 0.56rem 0.62rem;
        border-right: 1px solid #e5e7eb;
        border-bottom: 1px solid #e5e7eb;
    }

    .home-funds-assurance-label {
        color: #64748b;
        font-size: 0.96rem;
        line-height: 1.3;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .home-funds-assurance-value {
        margin-top: 0.16rem;
        color: #0f172a;
        font-size: 1.38rem;
        line-height: 1.18;
        font-weight: 800;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .home-funds-assurance-value.good { color: #15803d; }
    .home-funds-assurance-value.warn { color: #b45309; }
    .home-funds-assurance-value.risk { color: #dc2626; }
    .home-funds-assurance-value.pending { color: #64748b; }

    .home-funds-assurance-conclusion {
        padding: 0.56rem 0.66rem;
        border-radius: 8px;
        font-size: 0.98rem;
        line-height: 1.35;
        font-weight: 720;
    }

    .home-funds-assurance-conclusion.good {
        color: #166534;
        background: #ecfdf3;
    }

    .home-funds-assurance-conclusion.warn {
        color: #92400e;
        background: #fff7ed;
    }

    .home-funds-assurance-conclusion.risk {
        color: #991b1b;
        background: #fef2f2;
    }

    .home-funds-assurance-conclusion.pending {
        color: #475569;
        background: #f1f5f9;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini {
        gap: 0.72rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini-row {
        grid-template-columns: minmax(92px, 0.58fr) minmax(118px, 1fr) minmax(96px, 0.52fr);
        gap: 0.68rem;
        font-size: 0.96rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini-label {
        font-size: 0.96rem;
        font-weight: 720;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini-track {
        height: 0.72rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini-value {
        font-size: 1.22rem;
        font-weight: 800;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-note-grid {
        gap: 0.55rem;
        margin-top: 0.86rem;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-note {
        font-size: 0.94rem;
        line-height: 1.35;
    }

    .home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-note strong {
        font-size: 1.42rem;
        font-weight: 800;
    }

    .home-card-footnote {
        margin-top: 0.72rem;
        padding-top: 0.56rem;
        border-top: 1px solid var(--border-soft);
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.35;
    }

    .home-budget-compare {
        display: grid;
        gap: 0.9rem;
    }

    .home-budget-compare-row {
        display: grid;
        gap: 0.34rem;
        min-width: 0;
    }

    .home-budget-compare-top {
        display: grid;
        grid-template-columns: minmax(88px, 0.7fr) minmax(104px, 0.52fr) minmax(150px, 1fr);
        gap: 0.72rem;
        align-items: baseline;
        min-width: 0;
        font-size: 0.98rem;
    }

    .home-budget-compare-label {
        color: #3f3f46;
        font-weight: 760;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .home-budget-compare-value {
        color: #0f172a;
        font-weight: 820;
        font-size: 1.48rem;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
    }

    .home-budget-compare-gap {
        justify-self: end;
        color: #64748b;
        font-size: 0.98rem;
        font-weight: 720;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }

    .home-budget-compare-gap.good { color: #15803d; }
    .home-budget-compare-gap.warn { color: #b45309; }
    .home-budget-compare-gap.risk { color: #dc2626; }

    .home-budget-track {
        position: relative;
        height: 1.05rem;
        overflow: visible;
        border-radius: 999px;
        background: #edf2f7;
        box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.18);
    }

    .home-budget-fill {
        display: block;
        height: 100%;
        width: var(--fill-width, 0%);
        border-radius: 999px;
        background: #2b7de9;
    }

    .home-budget-fill.good { background: #2d9d78; }
    .home-budget-fill.warn { background: #d8912f; }
    .home-budget-fill.risk { background: #d65045; }

    .home-budget-time-marker {
        position: absolute;
        top: -0.24rem;
        bottom: -0.24rem;
        left: var(--benchmark-left, 0%);
        width: 3px;
        border-radius: 999px;
        background: #172033;
        box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
    }

    .home-budget-time-label {
        margin-top: 0.28rem;
        color: #64748b;
        font-size: 0.94rem;
        font-weight: 760;
        white-space: nowrap;
    }

    .home-budget-status-line {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin-top: 0.78rem;
        padding-top: 0.58rem;
        border-top: 1px solid var(--border-soft);
        color: #64748b;
        font-size: 0.94rem;
    }

    .home-budget-status-pill {
        display: inline-flex;
        align-items: center;
        max-width: 100%;
        border-radius: 999px;
        padding: 0.18rem 0.55rem;
        background: #f1f5f9;
        color: #18314f;
        font-weight: 760;
        white-space: nowrap;
    }

    .home-budget-status-pill.good { background: #ecfdf3; color: #15803d; }
    .home-budget-status-pill.warn { background: #fff7ed; color: #b45309; }
    .home-budget-status-pill.risk { background: #fef2f2; color: #dc2626; }

    .home-expense-donut-layout {
        display: grid;
        grid-template-columns: minmax(0, 0.64fr) minmax(0, 0.36fr);
        gap: 0.72rem;
        align-items: center;
        min-width: 0;
    }

    .home-expense-donut {
        width: clamp(320px, 32vw, 520px);
        max-width: 100%;
        aspect-ratio: 1;
        border-radius: 50%;
        background: var(--donut-gradient, #eef2f3);
        position: relative;
        margin: 0 auto;
        box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.16);
    }

    .home-expense-donut::after {
        content: "";
        position: absolute;
        inset: 26%;
        border-radius: 50%;
        background: #fff;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.14);
    }

    .home-expense-donut-center {
        position: absolute;
        z-index: 1;
        inset: 27%;
        display: grid;
        place-items: center;
        align-content: center;
        text-align: center;
        line-height: 1.18;
        color: #64748b;
        font-size: 0.95rem;
        font-weight: 700;
    }

    .home-expense-donut-center strong {
        display: block;
        margin-top: 0.16rem;
        color: #18314f;
        font-size: 1.38rem;
        font-weight: 840;
        white-space: nowrap;
    }

    .home-expense-legend {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.5rem;
        min-width: 0;
    }

    .home-expense-legend-row {
        display: grid;
        grid-template-columns: 0.7rem minmax(0, 1fr);
        gap: 0.42rem;
        align-items: start;
        min-width: 0;
    }

    .home-expense-dot {
        width: 0.7rem;
        height: 0.7rem;
        margin-top: 0.14rem;
        border-radius: 999px;
        background: var(--dot-color, #2b7de9);
    }

    .home-expense-legend-name {
        color: #334155;
        font-size: 0.96rem;
        font-weight: 760;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .home-expense-legend-meta {
        margin-top: 0.08rem;
        color: #64748b;
        font-size: 0.9rem;
        font-weight: 680;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .home-expense-bridge-rows {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.55rem;
        margin-top: 0.9rem;
    }

    .home-expense-bridge-row {
        border-top: 1px solid var(--border-soft);
        padding-top: 0.54rem;
        color: #64748b;
        font-size: 0.96rem;
        line-height: 1.35;
    }

    .home-expense-bridge-row strong {
        display: block;
        color: #18314f;
        margin-top: 0.1rem;
        font-size: 1.34rem;
        font-weight: 800;
    }

    .home-expense-bridge-row.risk strong { color: #dc2626; }

    .home-rank-dual {
        display: grid;
        gap: 0.58rem;
    }

    .home-rank-two-col {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.9rem;
        align-items: start;
    }

    .home-rank-column {
        min-width: 0;
        border: 1px solid #edf2f7;
        border-radius: 10px;
        background: #fbfdff;
        padding: 0.72rem;
    }

    .home-card-group-company-profit-rank .bi-panel-title {
        font-size: 1.32rem;
        line-height: 1.22;
        font-weight: 780;
    }

    .home-card-group-company-profit-rank .bi-panel-subtitle {
        font-size: 0.98rem;
        line-height: 1.4;
    }

    .home-rank-column-title {
        color: #18314f;
        font-size: 0.82rem;
        font-weight: 760;
        margin-bottom: 0.55rem;
    }

    .home-rank-table-head {
        margin: 0.08rem 0.72rem 0.46rem;
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 760;
    }

    .home-rank-column-head {
        display: grid;
        align-items: center;
        margin-bottom: 0.36rem;
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 760;
    }

    .home-rank-column-head span:last-child {
        text-align: right;
        color: #18314f;
    }

    .home-rank-dual-row {
        display: grid;
        grid-template-columns: minmax(92px, 0.55fr) minmax(140px, 1fr) minmax(76px, 0.36fr);
        gap: 0.55rem;
        align-items: center;
        font-size: 0.76rem;
    }

    .home-card-group-company-profit-rank .home-rank-dual-row,
    .home-card-group-company-profit-rank .home-rank-column-head {
        grid-template-columns: minmax(118px, 0.68fr) minmax(138px, 0.95fr) minmax(92px, 0.48fr) minmax(94px, 0.5fr);
        gap: 0.62rem;
    }

    .home-card-group-company-profit-rank .home-rank-column {
        padding: 0.9rem;
    }

    .home-card-group-company-profit-rank .home-rank-column-title {
        font-size: 1.16rem;
        line-height: 1.25;
        font-weight: 800;
        margin-bottom: 0.68rem;
    }

    .home-card-group-company-profit-rank .home-rank-table-head,
    .home-card-group-company-profit-rank .home-rank-column-head {
        font-size: 0.95rem;
    }

    .home-card-group-company-profit-rank .home-rank-column-head {
        margin-bottom: 0.5rem;
    }

    .home-card-group-company-profit-rank .home-rank-dual {
        gap: 0.72rem;
    }

    .home-card-group-company-profit-rank .home-rank-dual-row {
        font-size: 0.98rem;
    }

    .home-rank-dual-name {
        color: #3f3f46;
        font-weight: 680;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .home-rank-dual-bars {
        display: grid;
        gap: 0.2rem;
    }

    .home-card-group-company-profit-rank .home-rank-dual-name {
        font-size: 0.98rem;
        font-weight: 720;
    }

    .home-rank-dual-track {
        height: 0.38rem;
        overflow: hidden;
        border-radius: 999px;
        background: #eef2f3;
    }

    .home-card-group-company-profit-rank .home-rank-dual-track {
        height: 0.62rem;
    }

    .home-card-group-company-profit-rank .home-rank-dual-bars {
        gap: 0.3rem;
    }

    .home-rank-dual-fill {
        display: block;
        height: 100%;
        width: var(--fill-width, 0%);
        border-radius: 999px;
        background: #2b7de9;
    }

    .home-rank-dual-fill.profit { background: #2d9d78; }
    .home-rank-dual-fill.loss { background: #d65045; }
    .home-rank-dual-value {
        text-align: right;
        color: #52525b;
        font-weight: 700;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .home-card-group-company-profit-rank .home-rank-dual-value {
        display: grid;
        gap: 0.14rem;
        line-height: 1.2;
        font-size: 1.02rem;
        font-weight: 780;
    }

    .home-rank-dual-value .profit { color: #15803d; }
    .home-rank-dual-value .loss { color: #dc2626; }

    .home-rank-dual-margin {
        text-align: right;
        color: #475569;
        font-weight: 760;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .home-rank-dual-margin.profit { color: #15803d; }
    .home-rank-dual-margin.loss { color: #dc2626; }

    .home-card-group-company-profit-rank .home-rank-dual-margin {
        font-size: 1.02rem;
        font-weight: 800;
    }

    .home-anomaly-tags {
        display: flex;
        gap: 0.35rem;
        flex-wrap: wrap;
        margin-top: 0.72rem;
    }

    .home-anomaly-tag {
        display: inline-flex;
        align-items: center;
        gap: 0.28rem;
        border-radius: 999px;
        padding: 0.22rem 0.5rem;
        background: #fff4d6;
        color: #9a5b00;
        font-size: 0.73rem;
        font-weight: 760;
    }

    .home-risk-summary-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        border-top: 1px solid var(--border-soft);
        border-bottom: 1px solid var(--border-soft);
        margin: 0.16rem 0 0.9rem;
    }

    .home-risk-summary-item {
        padding: 0.62rem 0.72rem;
        color: #64748b;
        font-size: 0.94rem;
        line-height: 1.25;
        text-align: center;
        border-right: 1px solid var(--border-soft);
    }

    .home-risk-summary-item:last-child {
        border-right: 0;
    }

    .home-risk-summary-item strong {
        display: block;
        margin-top: 0.14rem;
        color: #18314f;
        font-size: 1.5rem;
        font-weight: 820;
        font-variant-numeric: tabular-nums;
    }

    .home-risk-summary-item.tight strong { color: #dc2626; }
    .home-risk-summary-item.watch strong { color: #b45309; }
    .home-risk-summary-item.safe strong { color: #15803d; }

    .home-risk-list {
        display: grid;
        overflow: hidden;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #fff;
    }

    .home-risk-list-title {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(82px, 0.34fr) minmax(86px, 0.38fr);
        gap: 0.62rem;
        align-items: center;
        padding: 0.56rem 0.68rem;
        color: #64748b;
        background: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        font-size: 0.9rem;
        font-weight: 760;
    }

    .home-risk-list-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(82px, 0.34fr) minmax(86px, 0.38fr);
        gap: 0.62rem;
        align-items: center;
        min-width: 0;
        padding: 0.58rem 0.68rem;
        border-bottom: 1px solid #eef2f7;
        font-size: 0.96rem;
    }

    .home-risk-list-row:nth-child(even) {
        background: #fbfdff;
    }

    .home-risk-list-row:last-child {
        border-bottom: 0;
    }

    .home-risk-company {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: #1f2937;
        font-weight: 760;
    }

    .home-risk-ratio {
        text-align: right;
        color: #0f172a;
        font-weight: 820;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
    }

    .home-risk-status {
        justify-self: end;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 4.8rem;
        padding: 0.22rem 0.55rem;
        border-radius: 999px;
        font-size: 0.9rem;
        font-weight: 820;
        white-space: nowrap;
    }

    .home-risk-status.tight {
        color: #b91c1c;
        background: #fee2e2;
    }

    .home-risk-status.watch {
        color: #b45309;
        background: #fef3c7;
    }

    .home-risk-status.safe {
        color: #047857;
        background: #dcfce7;
    }

    .home-risk-status.pending {
        color: #475569;
        background: #e2e8f0;
    }

    .bi-alert-list {
        display: grid;
        gap: 0.55rem;
    }

    .bi-alert-item {
        border: 1px solid #f1d2cc;
        border-left: 4px solid #d65045;
        background: #fff7f5;
        border-radius: 8px;
        padding: 0.65rem 0.75rem;
        color: #7a271a;
        font-size: 0.8rem;
        line-height: 1.45;
    }

    .bi-alert-item.watch {
        border-color: #f2dfb4;
        border-left-color: #d8912f;
        background: #fffaf0;
        color: #6f4c10;
    }

    .bi-empty {
        border: 1px solid #cfe9dd;
        background: #f2fbf7;
        border-radius: 8px;
        padding: 0.8rem;
        color: #1f6f4a;
        font-size: 0.85rem;
    }

    @media (max-width: 1100px) {
        html,
        body,
        [data-testid="stAppViewContainer"] {
            min-width: 0;
        }
        section[data-testid="stSidebar"] {
            width: 17rem !important;
            min-width: 17rem !important;
        }
        .main > .block-container {
            padding: 0.95rem 1rem 1.5rem;
        }
        .bi-hero,
        .bi-two-col,
        .bi-section-grid {
            grid-template-columns: 1fr;
        }
        .home-card-group-grid > .home-card-group-company-profit-rank {
            grid-column: auto;
        }
        .home-rank-two-col {
            grid-template-columns: 1fr;
        }
        .home-card-group-company-profit-rank .home-rank-dual-row,
        .home-card-group-company-profit-rank .home-rank-column-head {
            grid-template-columns: minmax(92px, 0.62fr) minmax(108px, 0.88fr) minmax(66px, 0.4fr) minmax(82px, 0.55fr);
            gap: 0.48rem;
        }
        .home-expense-donut-layout {
            grid-template-columns: 1fr;
        }
        .home-expense-donut {
            width: min(360px, 72vw);
        }
        .bi-kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 720px) {
        .bi-kpi-grid,
        .bi-hero-side,
        .bi-micro {
            grid-template-columns: 1fr;
        }
        .home-card-group-company-profit-rank .home-rank-dual-row,
        .home-card-group-company-profit-rank .home-rank-column-head {
            grid-template-columns: minmax(78px, 0.62fr) minmax(84px, 0.88fr) minmax(58px, 0.4fr) minmax(76px, 0.55fr);
            gap: 0.34rem;
            font-size: 0.72rem;
        }
        .home-budget-compare-top {
            grid-template-columns: minmax(62px, 0.58fr) minmax(72px, 0.44fr) minmax(0, 1fr);
            gap: 0.36rem;
        }
        .home-budget-compare-gap,
        .home-budget-time-label,
        .home-budget-status-line {
            font-size: 0.84rem;
        }
        .home-funds-assurance-grid {
            grid-template-columns: 1fr;
        }
        .home-expense-legend {
            grid-template-columns: 1fr;
        }
        .home-expense-donut {
            width: min(300px, 78vw);
        }
    }

    .app-footer {
        text-align: center;
        padding: 1.75rem 0 0.5rem;
        font-size: 0.75rem;
        color: #86868b;
        border-top: 1px solid var(--border-soft);
        margin-top: 2rem;
    }

    hr.divider {
        border: none;
        height: 1px;
        background: var(--border-soft);
        margin: 1.25rem 0;
    }
</style>
"""

# ============================================================================
# 初始化与辅助函数
# ============================================================================

def init_app():
    if "db_initialized" not in st.session_state:
        with st.spinner("🔄 正在初始化数据库..."):
            try:
                init_database()
                st.session_state.db_initialized = True
            except Exception as e:
                st.error(f"数据库初始化失败: {e}")
                st.session_state.db_initialized = False
    try:
        st.session_state.companies = get_companies()
    except Exception:
        st.session_state.companies = pd.DataFrame(columns=["code", "name"])

def _get_year_month_options(table: str = "account_balance") -> tuple:
    years, months = [], []
    try:
        periods_df = execute_sql(f"SELECT DISTINCT period FROM {table} ORDER BY period DESC")
        periods = periods_df["period"].tolist() if len(periods_df) > 0 else []
        years = sorted(set(p[:4] for p in periods if len(p) == 6), reverse=True)
        months = sorted(set(p[4:6] for p in periods if len(p) == 6))
    except Exception:
        pass
    return years, months


def _budget_actual_db_signature() -> tuple[str, tuple[tuple[str, int, int, int], ...]]:
    path = get_db_path()
    signature: list[tuple[str, int, int, int]] = []
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            stat = candidate.stat()
            signature.append((str(candidate), 1, stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(candidate), 0, 0, 0))
    return str(path), tuple(signature)


def _budget_period_months(periods: list[str]) -> dict[str, list[str]]:
    by_year: dict[str, set[str]] = {}
    for value in periods:
        period = str(value or "").strip()
        if not re.fullmatch(r"\d{6}", period):
            continue
        month = period[4:6]
        if "01" <= month <= "12":
            by_year.setdefault(period[:4], set()).add(month)
    return {year: sorted(months) for year, months in by_year.items()}


@st.cache_data(show_spinner=False, ttl=60)
def _budget_actual_period_months_cached(
    db_path: str,
    db_signature: tuple[tuple[str, int, int, int], ...],
) -> dict[str, list[str]]:
    try:
        rows = execute_sql(
            """
            SELECT DISTINCT period
            FROM pl_detail
            WHERE period IS NOT NULL
              AND period GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'
              AND item_name IN (:revenue_item, :profit_item)
              AND ytd_amount IS NOT NULL
              AND ABS(COALESCE(ytd_amount, 0)) > 0.000001
            ORDER BY period
            """,
            {"revenue_item": PL_REVENUE_ITEM, "profit_item": PL_NET_PROFIT_ITEM},
        )
    except Exception:
        return {}
    periods = rows["period"].astype(str).tolist() if rows is not None and len(rows) else []
    return _budget_period_months(periods)


def _budget_actual_period_months() -> dict[str, list[str]]:
    db_path, db_signature = _budget_actual_db_signature()
    return _budget_actual_period_months_cached(db_path, db_signature)


def _budget_default_month(months: list[str], has_actual_months: bool) -> str:
    if has_actual_months and months:
        return months[-1]
    safe_months = months or [f"{idx:02d}" for idx in range(1, 13)]
    return "03" if "03" in safe_months else safe_months[0]


def _resolve_budget_year_month_state(
    years: list[str],
    months_by_year: dict[str, list[str]],
    stored_year: str | None,
    stored_month: str | None,
    previous_page: str | None,
    last_seen_year: str | None,
) -> tuple[str, str, list[str], bool]:
    safe_years = years or ["2026"]
    selected_year = str(stored_year or "")
    reset_year = selected_year not in safe_years
    if reset_year:
        selected_year = safe_years[0]

    actual_months = months_by_year.get(selected_year, [])
    has_actual_months = bool(actual_months)
    month_options = actual_months or [f"{idx:02d}" for idx in range(1, 13)]
    default_month = _budget_default_month(month_options, has_actual_months)

    entering_budget = previous_page != "全面预算"
    year_changed = bool(last_seen_year) and str(last_seen_year) != selected_year
    selected_month = str(stored_month or "")
    if entering_budget or reset_year or year_changed or selected_month not in month_options:
        selected_month = default_month

    return selected_year, selected_month, month_options, has_actual_months


def _prepare_budget_year_month_state(years: list[str], months_by_year: dict[str, list[str]]) -> tuple[list[str], bool]:
    selected_year, selected_month, month_options, has_actual_months = _resolve_budget_year_month_state(
        years,
        months_by_year,
        st.session_state.get("budget_year"),
        st.session_state.get("budget_month"),
        st.session_state.get("_last_rendered_page"),
        st.session_state.get("_budget_last_seen_year"),
    )
    st.session_state["budget_year"] = selected_year
    st.session_state["budget_month"] = selected_month
    return month_options, has_actual_months


def _cn_cols(df: pd.DataFrame, col_map: dict, keep_only: bool = True) -> pd.DataFrame:
    df = df.rename(columns=col_map)
    if keep_only:
        cols = [c for c in col_map.values() if c in df.columns]
        df = df[cols]
    return df


def _read_export_bytes(file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        content = f.read()
    try:
        os.unlink(file_path)
    except OSError:
        pass
    return content


def _company_label(company_codes, company_dict: dict) -> str:
    if isinstance(company_codes, str):
        company_codes = [company_codes]
    codes = [c for c in company_codes if c]
    if len(codes) == 1:
        code = codes[0]
        return f"{code} - {company_dict.get(code, code)}"
    return "多公司"


def _period_label(periods) -> str:
    if isinstance(periods, str):
        periods = [periods]
    periods = [str(p) for p in periods if p]
    return periods[0] if len(periods) == 1 else "、".join(periods)


def _fmt_money(value) -> str:
    try:
        return f"{float(value) / 10000:,.1f} 万"
    except (TypeError, ValueError):
        return "-"


def _fmt_percent(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_number(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_kpi_value(kpi: dict) -> str:
    if kpi.get("type") == "money":
        return _fmt_money(kpi.get("value"))
    if kpi.get("type") == "percent":
        return _fmt_percent(kpi.get("value"))
    return _fmt_number(kpi.get("value"))


def _fmt_kpi_delta(kpi: dict) -> str:
    label = kpi.get("label")
    delta = kpi.get("delta")
    if delta is None:
        return ""
    if label == "本月收入":
        return f"年度完成 {_fmt_percent(delta)}"
    if label == "本月净利润":
        return f"净利率 {_fmt_percent(delta)}"
    if label == "货币资金":
        return f"周转 {_fmt_number(delta)} 月"
    return _fmt_percent(delta)


def _fmt_kpi_comparison_value(item: dict | None) -> str:
    if not item:
        return "暂无"
    value = item.get("value")
    if value is None:
        return "暂无"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "暂无"
    sign = "+" if number > 0 else ""
    if item.get("mode") == "point":
        return f"{sign}{number * 100:.1f}pct"
    return f"{sign}{number * 100:.1f}%"


def _kpi_comparison_class(item: dict | None) -> str:
    if not item or item.get("value") is None:
        return "neutral"
    try:
        number = float(item.get("value"))
    except (TypeError, ValueError):
        return "neutral"
    if number > 0:
        return "good"
    if number < 0:
        return "risk"
    return "neutral"


def _kpi_comparisons_html(kpi: dict) -> str:
    comparisons = kpi.get("comparisons") or {}
    if not comparisons:
        return ""
    items = []
    for label in ("同比", "环比"):
        item = comparisons.get(label)
        items.append(
            f'<span class="bi-kpi-trend {_kpi_comparison_class(item)}">'
            f'{_html(label)} {_html(_fmt_kpi_comparison_value(item))}</span>'
        )
    return f'<div class="bi-kpi-trends">{"".join(items)}</div>'


def _progress_value(value) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _render_kpi_card(kpi: dict) -> None:
    delta = _fmt_kpi_delta(kpi)
    delta_html = f'<div class="label">{delta}</div>' if delta else ""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="label">{kpi.get("label", "")}</div>
            <div class="value">{_fmt_kpi_value(kpi)}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_ratio_ui(numerator, denominator) -> float | None:
    denominator = _safe_float(denominator)
    if abs(denominator) < 1e-9:
        return None
    return _safe_float(numerator) / denominator


def _fmt_money_compact(value) -> str:
    amount = _safe_float(value)
    if abs(amount) >= 100000000:
        return f"{amount / 100000000:,.2f} 亿"
    if abs(amount) >= 10000:
        return f"{amount / 10000:,.1f} 万"
    return f"{amount:,.0f}"


def _html(value) -> str:
    return escape(str(value if value is not None else ""))


def _render_html(markup: str) -> None:
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def _progress_width(value) -> str:
    return f"{_progress_value(value) * 100:.1f}%"


def _progress_class(value, benchmark=None) -> str:
    current = _safe_float(value)
    if benchmark is None:
        benchmark = 0.8
    benchmark = _safe_float(benchmark)
    if current >= benchmark:
        return "good"
    if current >= max(benchmark * 0.75, 0.05):
        return "warn"
    return "risk"


def _kpi_card_class(kpi: dict) -> str:
    label = str(kpi.get("label", ""))
    value = _safe_float(kpi.get("value"))
    if "平衡差" in label and abs(value) > 1:
        return "risk"
    if "净利润" in label or "净利率" in label or "利润" in label:
        return "profit"
    if "货币" in label or "预收" in label:
        return "cash"
    if "平衡差" in label:
        return "neutral"
    return ""


def _render_bi_kpi_grid(
    kpis: list[dict],
    drill_label_map: dict[str, str] | None = None,
    selected_metric_key: str | None = None,
    extra_grid_class: str = "",
) -> None:
    drill_label_map = drill_label_map or {}
    cards = []
    for kpi in kpis:
        label = str(kpi.get("label", ""))
        delta = _fmt_kpi_delta(kpi)
        delta_html = f'<div class="bi-kpi-delta">{_html(delta)}</div>' if delta else ""
        trends_html = _kpi_comparisons_html(kpi)
        value_text = _fmt_kpi_value(kpi)
        drill_key = drill_label_map.get(label)
        card_kind = _kpi_card_class(kpi)
        if drill_key and drill_key == selected_metric_key:
            card_classes = "bi-kpi-card selected" + (f" {card_kind}" if card_kind else "")
        else:
            card_classes = "bi-kpi-card" + (f" {card_kind}" if card_kind else "")
        if drill_key:
            is_selected = drill_key == selected_metric_key
            href = _app_query_href() if is_selected else _app_query_href({"drill_metric": drill_key})
            title = "点击收起" if is_selected else "点击展开下钻"
            value_markup = (
                f'<a class="bi-kpi-value-link" href="{href}" target="_top" '
                f'title="{_html(title)}">{_html(value_text)}</a>'
            )
        else:
            value_markup = _html(value_text)
        cards.append(
            f"""
            <div class="{_html(card_classes)}">
                <div class="bi-kpi-label">{_html(label)}</div>
                <div class="bi-kpi-value">{value_markup}</div>
                {delta_html}
                {trends_html}
            </div>
            """
        )
    grid_class = "bi-kpi-grid" + (f" {_html(extra_grid_class)}" if extra_grid_class else "")
    _render_html(f'<div class="{grid_class}">{"".join(cards)}</div>')


def _progress_row_html(label: str, value, actual=None, target=None, benchmark=None) -> str:
    detail = ""
    if actual is not None or target is not None:
        detail = f"{_fmt_money_compact(actual)} / {_fmt_money_compact(target)}"
    elif benchmark is not None:
        detail = f"理论进度 {_fmt_percent(benchmark)}"
    return f"""
        <div class="bi-progress-row">
            <div class="bi-progress-top">
                <span>{_html(label)}</span>
                <span>{_html(_fmt_percent(value))}</span>
            </div>
            <div class="bi-progress-track">
                <div class="bi-progress-fill {_progress_class(value, benchmark)}" style="width:{_progress_width(value)}"></div>
            </div>
            <div class="bi-panel-subtitle">{_html(detail)}</div>
        </div>
    """


def _panel_html(title: str, subtitle: str, body: str) -> str:
    subtitle_html = f'<div class="bi-panel-subtitle">{_html(subtitle)}</div>' if subtitle else ""
    return f"""
        <div class="bi-panel">
            <div class="bi-panel-title">{_html(title)}</div>
            {subtitle_html}
            {body}
        </div>
    """


HOME_CARD_GROUP_CONFIG: dict[str, dict[str, str]] = {
    "budget_execution": {
        "label": "预算执行",
        "title": "预算执行明细",
        "subtitle": "复用全面预算总览口径，按经营单位查看收入与利润进度。",
    },
    "operating_summary": {
        "label": "经营汇总",
        "title": "经营汇总明细",
        "subtitle": "复用收入成本费用表经营口径，按公司查看收入、成本和利润。",
    },
    "expense_analysis": {
        "label": "费用分析",
        "title": "费用分析明细 · 按模块",
        "subtitle": "查看各模块费用构成及占集团成本费用比。",
    },
    "operating_anomaly": {
        "label": "经营异常",
        "title": "经营异常明细",
        "subtitle": "沿用当前暂定同比/环比阈值，展示经营波动异常；待后续专项复核。",
    },
    "company_profit_rank": {
        "label": "公司收入利润排行",
        "title": "公司收入利润排行明细",
        "subtitle": "沿用现有 pl_detail 驾驶舱口径，展示公司收入、利润和变化；待后续专项复核。",
    },
    "funds_safety": {
        "label": "资金安全",
        "title": "资金安全明细",
        "subtitle": "沿用现有资金预警口径，展示单体公司资金构成；待后续专项复核。",
    },
    "funds_turnover_risk": {
        "label": "资金周转风险",
        "title": "资金周转风险明细",
        "subtitle": "沿用现有资金预警口径，默认展示资金紧张和资金关注公司；待后续专项复核。",
    },
}

HOME_OPERATING_ANOMALY_THRESHOLDS: dict[str, float] = {
    "收入同比下降": -0.20,
    "收入环比下降": -0.20,
    "利润同比下降": -0.30,
    "利润环比下降": -0.30,
    "成本费用环比上升": 0.20,
    "净利率明显下滑": -0.05,
}
HOME_CONSOLIDATION_RANK_EXCLUDED_CODES = {"10101", "10102", "10107", "10108", "10118"}

HOME_OPERATING_CARD_GROUPS: list[dict[str, str]] = [
    {"key": "management", "label": "管理中心", "code": "101"},
    {"key": "quality", "label": "素质中心", "code": "10101"},
    {"key": "international", "label": "国际教育", "code": "10102"},
    {"key": "kindergarten", "label": "幼儿园", "code": "10107"},
    {"key": "school", "label": "多维学校", "code": "10108"},
    {"key": "youth", "label": "青少年宫", "code": "10118"},
    {"key": "eryu", "label": "尔遇书馆", "code": "10204"},
]

HOME_MANAGEMENT_CENTER_CODE = "101"
HOME_NON_SUBJECT_CENTER_CODE = "1010101"
HOME_ERYU_CENTER_CODE = "10204"
HOME_SONGSHANHU_CODE = "101010138"
HOME_MAIN_REVENUE_ITEM = "主营业务收入"
HOME_MANAGEMENT_FEE_ITEM = "管理费服务费"
HOME_COMPARISON_MIN_DENOMINATOR = 1e-6
HOME_UNCOMPARABLE_TEXT = "不可比"


def _home_metric_missing(value) -> bool:
    try:
        return value is None or pd.isna(value)
    except (TypeError, ValueError):
        return value is None


def _home_relative_change_value(current, previous):
    if _home_metric_missing(current) or _home_metric_missing(previous):
        return None
    previous_value = _safe_float(previous)
    if abs(previous_value) < HOME_COMPARISON_MIN_DENOMINATOR:
        return HOME_UNCOMPARABLE_TEXT
    return (_safe_float(current) - previous_value) / abs(previous_value)


def _home_profit_change_value(current, previous):
    if _home_metric_missing(current) or _home_metric_missing(previous):
        return None
    current_value = _safe_float(current)
    previous_value = _safe_float(previous)
    if abs(previous_value) < HOME_COMPARISON_MIN_DENOMINATOR:
        return HOME_UNCOMPARABLE_TEXT
    if previous_value > 0 and current_value < 0:
        return "由盈转亏"
    if previous_value < 0 <= current_value:
        return "扭亏"
    if previous_value < 0 and current_value < previous_value:
        return "亏损扩大"
    if previous_value < 0 and previous_value <= current_value < 0:
        return "亏损收窄"
    return (current_value - previous_value) / abs(previous_value)


def _home_comparison_degree(value) -> float:
    if isinstance(value, str):
        return 1.0
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        return 0.0
    return abs(_safe_float(value))


def _home_metric_has_source_map(rows: pd.DataFrame) -> set[tuple[str, str]]:
    if rows is None or rows.empty:
        return set()
    target = rows[rows["item_name"].astype(str).isin({PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM, PL_COST_TOTAL_ITEM})].copy()
    preferred = preferred_pl_detail_rows(target)
    if preferred.empty:
        return set()
    return {
        (str(row.get("company_code") or ""), str(row.get("item_name") or ""))
        for row in preferred.to_dict("records")
    }


def _home_card_group_href(group_key: str, selected_group_key: str | None = None) -> str:
    return _app_query_href() if group_key == selected_group_key else _app_query_href({"home_group": str(group_key)})


def _home_card_group_wrap(group_key: str, selected_group_key: str | None, panel_html: str) -> str:
    active_class = " active" if group_key == selected_group_key else ""
    group_class = f" home-card-group-{str(group_key).replace('_', '-')}"
    title = "点击收起" if active_class else "点击查看明细"
    return (
        f'<a class="home-card-group-link{group_class}{active_class}" href="{_html(_home_card_group_href(group_key, selected_group_key))}" '
        f'target="_top" title="{_html(title)}">{panel_html}</a>'
    )


def _home_card_fill_width(value) -> str:
    return f"{_progress_value(value) * 100:.1f}%"


def _home_card_benchmark_left(value) -> str:
    return f"{_progress_value(value) * 100:.1f}%"


def _home_card_status_class(value, benchmark=None) -> str:
    return _progress_class(value, benchmark)


def _home_budget_gap_phrase(value) -> str:
    if _budget_value_missing(value):
        return "暂无偏离"
    gap = _safe_float(value)
    direction = "超前" if gap >= 0 else "滞后"
    return f"{direction} {abs(gap) * 100:.1f} 个百分点"


def _home_budget_gap_class(value) -> str:
    if _budget_value_missing(value):
        return "warn"
    return "good" if _safe_float(value) >= 0 else "risk"


def _home_budget_status_class(status: str | None) -> str:
    text = str(status or "")
    if any(keyword in text for keyword in ("超前", "改善", "正常")):
        return "good"
    if any(keyword in text for keyword in ("滞后", "亏损", "风险")):
        return "risk"
    return "warn"


def _home_budget_compare_row(label: str, completion, theory, gap) -> str:
    gap_class = _home_budget_gap_class(gap)
    return f"""
        <div class="home-budget-compare-row">
            <div class="home-budget-compare-top">
                <div class="home-budget-compare-label">{_html(label)}</div>
                <div class="home-budget-compare-value">{_html(_fmt_percent(completion))}</div>
                <div class="home-budget-compare-gap {gap_class}" title="{_html(_home_budget_gap_phrase(gap))}">
                    {_html(_home_budget_gap_phrase(gap))}
                </div>
            </div>
            <div class="home-budget-track" style="--benchmark-left:{_home_card_benchmark_left(theory)}">
                <span class="home-budget-fill {_home_card_status_class(completion, theory)}" style="--fill-width:{_home_card_fill_width(completion)}"></span>
                <span class="home-budget-time-marker" aria-hidden="true"></span>
            </div>
            <div class="home-budget-time-label">时间进度 {_html(_fmt_percent(theory))}</div>
        </div>
    """


def _home_budget_card_summary(budget: dict) -> dict:
    overview = budget.get("progress") if isinstance(budget, dict) else None
    total = _budget_total_row(overview) if isinstance(overview, pd.DataFrame) else {}
    theory = budget.get("theory_completion") if isinstance(budget, dict) else None
    if theory is None:
        theory = total.get("时间进度")
    return {
        "income_completion": total.get("收入完成率", budget.get("income_completion") if isinstance(budget, dict) else None),
        "profit_completion": total.get("利润完成率", budget.get("profit_completion") if isinstance(budget, dict) else None),
        "theory_completion": theory,
        "income_gap": total.get("收入进度差"),
        "profit_gap": total.get("利润进度差"),
        "status": total.get("状态"),
        "income_actual": total.get("收入实际", budget.get("income_actual_ytd") if isinstance(budget, dict) else None),
        "profit_actual": total.get("利润实际", budget.get("profit_actual_ytd") if isinstance(budget, dict) else None),
    }


def _render_budget_execution_panel(budget: dict, selected_group_key: str | None = None) -> str:
    summary = _home_budget_card_summary(budget or {})
    theory = summary.get("theory_completion")
    income_completion = summary.get("income_completion")
    profit_completion = summary.get("profit_completion")
    income_gap = summary.get("income_gap")
    profit_gap = summary.get("profit_gap")
    status = summary.get("status") or "暂无"
    status_class = _home_budget_status_class(status)
    body = f"""
        <div class="home-budget-compare">
            {_home_budget_compare_row("收入完成", income_completion, theory, income_gap)}
            {_home_budget_compare_row("利润完成", profit_completion, theory, profit_gap)}
        </div>
        <div class="home-budget-status-line">
            <span>预算进度</span>
            <span class="home-budget-status-pill {status_class}">综合状态：{_html(status)}</span>
        </div>
    """
    panel = _panel_html("预算执行", "收入、利润对照当前时间进度", body)
    return _home_card_group_wrap("budget_execution", selected_group_key, panel)


def _render_budget_panel(budget: dict) -> str:
    theory = budget.get("theory_completion")
    body = (
        _progress_row_html(
            "收入预算完成",
            budget.get("income_completion"),
            budget.get("income_actual_ytd"),
            budget.get("income_target"),
            theory,
        )
        + _progress_row_html(
            "利润预算完成",
            budget.get("profit_completion"),
            budget.get("profit_actual_ytd"),
            budget.get("profit_target"),
            theory,
        )
    )
    body += f'<div class="bi-panel-subtitle">当前理论进度 {_html(_fmt_percent(theory))}</div>'
    return _panel_html("预算执行", "收入与利润分开看，先抓偏离理论进度的项目", body)


def _operating_summary_card_summary(income: dict) -> dict:
    revenue = _safe_float(income.get("revenue")) if isinstance(income, dict) else 0.0
    cost_total = _safe_float(income.get("cost_total", income.get("cost_run_rate"))) if isinstance(income, dict) else 0.0
    net_profit = _safe_float(income.get("net_profit")) if isinstance(income, dict) else 0.0
    net_margin = _safe_ratio_ui(net_profit, revenue)
    return {
        "revenue": revenue,
        "cost_total": cost_total,
        "net_profit": net_profit,
        "net_margin": net_margin,
    }


def _render_operating_summary_panel(income: dict, selected_group_key: str | None = None) -> str:
    summary = _operating_summary_card_summary(income or {})
    max_value = max(abs(summary["revenue"]), abs(summary["cost_total"]), abs(summary["net_profit"]), 1.0)

    def row(label: str, value: float, css_class: str = "") -> str:
        width = min(abs(_safe_float(value)) / max_value, 1.0) * 100
        sign_class = "negative" if _safe_float(value) < 0 else "positive"
        fill_class = css_class or sign_class
        return f"""
            <div class="home-card-mini-row">
                <div class="home-card-mini-label">{_html(label)}</div>
                <div class="home-card-mini-track">
                    <span class="home-card-mini-fill {fill_class}" style="--fill-width:{width:.1f}%"></span>
                </div>
                <div class="home-card-mini-value">{_html(_fmt_money_compact(value))}</div>
            </div>
        """

    net_margin = summary["net_margin"]
    margin_text = _fmt_percent(net_margin)
    margin_class = "risk" if _safe_float(net_margin) < 0 else "good"
    body = f"""
        <div class="home-card-mini">
            {row("经营收入", summary["revenue"], "good")}
            {row("成本费用", summary["cost_total"], "warn")}
            {row("经营净利润", summary["net_profit"])}
        </div>
        <div class="home-card-note-grid">
            <div class="home-card-note">净利率<strong class="{margin_class}">{_html(margin_text)}</strong></div>
        </div>
        <div class="home-card-footnote">经营收入 - 成本费用合计 = 经营净利润</div>
    """
    panel = _panel_html("经营汇总", "收入、成本、利润与净利率", body)
    return _home_card_group_wrap("operating_summary", selected_group_key, panel)


@st.cache_data(show_spinner=False, ttl=120)
def _home_expense_analysis_for_scope(period: str, company_codes: tuple[str, ...]) -> dict:
    source_df = get_operating_summary_source_detail(period, list(company_codes))
    return build_focus_expense_analysis(source_df)


HOME_EXPENSE_DONUT_COLORS = (
    "#2563eb",
    "#16a34a",
    "#f97316",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
)


def _home_expense_donut_html(categories: pd.DataFrame) -> str:
    view = categories.copy()
    view["_amount"] = pd.to_numeric(view.get("本月金额", 0), errors="coerce").fillna(0.0)
    rows = view.to_dict("records")
    positive_total = sum(max(_safe_float(row.get("_amount")), 0.0) for row in rows)
    six_total = sum(_safe_float(row.get("_amount")) for row in rows)
    if positive_total <= 1e-9:
        return '<div class="bi-empty">暂无六类重点费用数据</div>'

    segments: list[str] = []
    legend_rows: list[str] = []
    cursor = 0.0
    for idx, item in enumerate(rows):
        color = HOME_EXPENSE_DONUT_COLORS[idx % len(HOME_EXPENSE_DONUT_COLORS)]
        amount = _safe_float(item.get("_amount"))
        slice_amount = max(amount, 0.0)
        start = cursor
        cursor += slice_amount / positive_total * 360.0
        if slice_amount > 0:
            segments.append(f"{color} {start:.2f}deg {cursor:.2f}deg")
        ratio = amount / six_total if abs(six_total) > 1e-9 else None
        label = str(item.get("费用类别", ""))
        legend_rows.append(
            f"""
            <div class="home-expense-legend-row">
                <span class="home-expense-dot" style="--dot-color:{color}"></span>
                <div>
                    <div class="home-expense-legend-name" title="{_html(label)}">{_html(label)}</div>
                    <div class="home-expense-legend-meta" title="{_html(_fmt_money_compact(amount))}">{_html(_fmt_percent(ratio))} · {_html(_fmt_money_compact(amount))}</div>
                </div>
            </div>
            """
        )
    gradient = ", ".join(segments) if segments else "#eef2f3 0deg 360deg"
    return f"""
        <div class="home-expense-donut-layout">
            <div class="home-expense-donut" style="--donut-gradient:conic-gradient({gradient})">
                <div class="home-expense-donut-center">
                    六类重点费用合计
                    <strong>{_html(_fmt_money_compact(six_total))}</strong>
                </div>
            </div>
            <div class="home-expense-legend">{"".join(legend_rows)}</div>
        </div>
    """


def _render_expense_analysis_panel(analysis: dict, selected_group_key: str | None = None) -> str:
    categories = analysis.get("categories") if isinstance(analysis, dict) else pd.DataFrame()
    management = analysis.get("management_fee", {}) if isinstance(analysis, dict) else {}
    bridge = analysis.get("expense_bridge", {}) if isinstance(analysis, dict) else {}
    if not isinstance(categories, pd.DataFrame) or categories.empty:
        body = '<div class="bi-empty">暂无六类重点费用数据</div>'
    else:
        body = _home_expense_donut_html(categories)
    body += f"""
        <div class="home-expense-bridge-rows">
            <div class="home-expense-bridge-row">管理费服务费<strong>{_html(_fmt_money_compact(management.get("amount")))}</strong></div>
            <div class="home-expense-bridge-row {'risk' if bridge.get("status") == "warning" else ''}">{_html(bridge.get("label", "其他费用"))}<strong>{_html(_fmt_money_compact(bridge.get("check_difference") if bridge.get("status") == "warning" else bridge.get("other_fee")))}</strong></div>
        </div>
        <div class="home-card-footnote">{_html(_expense_bridge_sentence(bridge))}</div>
    """
    panel = _panel_html("费用分析", "六类重点费用占比与成本桥接", body)
    return _home_card_group_wrap("expense_analysis", selected_group_key, panel)


def _home_expense_analysis_detail_for_scope(period: str, company_codes: list[str]) -> pd.DataFrame:
    try:
        source_df = get_operating_summary_source_detail(period, list(company_codes))
    except Exception:
        source_df = pd.DataFrame()
    return _home_expense_module_detail_from_source(source_df, company_codes)


def _home_expense_module_detail_from_source(source_df: pd.DataFrame, company_codes: list[str]) -> pd.DataFrame:
    columns = [
        "模块/公司",
        "人工成本",
        "租金水电物业",
        "折旧摊销",
        "交际接待交通",
        "办公行政",
        "财务费用",
        "管理费服务费",
        "其他费用（或待核对差额）",
        "成本费用合计",
        "占集团成本费用比",
    ]
    if source_df is None or source_df.empty:
        return pd.DataFrame(columns=columns)

    source = source_df.copy()
    for column in ["source_item_name", "company_name", "company_code", "account_code"]:
        if column not in source.columns:
            source[column] = ""
    if "current_amount" not in source.columns:
        source["current_amount"] = 0.0
    source["company_code"] = source["company_code"].astype(str).str.strip()
    source["company_name"] = source["company_name"].astype(str).str.strip()
    source["source_item_name"] = source["source_item_name"].astype(str).str.strip()
    source["current_amount"] = pd.to_numeric(source["current_amount"], errors="coerce").fillna(0.0)
    pseudo_names = {"合计", "合并", "总计"}
    source = source[
        ~source["company_code"].isin(pseudo_names)
        & ~source["company_name"].isin(pseudo_names)
    ].copy()
    if source.empty:
        return pd.DataFrame(columns=columns)

    source_name_map = {
        str(row.get("company_code")): str(row.get("company_name"))
        for row in source[["company_code", "company_name"]].drop_duplicates().to_dict("records")
        if str(row.get("company_code") or "") and str(row.get("company_name") or "")
    }
    detail = source[source.apply(lambda row: _is_income_cost_detail_row(row.to_dict()), axis=1)].copy()
    raw_rows: list[dict] = []

    for group in _operating_card_group_scopes(company_codes):
        group_codes = [str(code) for code in group.get("codes", []) if str(code)]
        if not group_codes:
            continue
        group_source = source[source["company_code"].isin(group_codes)].copy()
        if group_source.empty:
            continue
        group_detail = detail[detail["company_code"].isin(group_codes)].copy()
        category_amounts: dict[str, float] = {}
        for rule in EXPENSE_FOCUS_CATEGORY_RULES:
            matched = group_detail[group_detail["source_item_name"].isin(rule["items"])]
            category_amounts[rule["category"]] = _safe_float(matched["current_amount"].sum()) if len(matched) else 0.0
        management_rows = group_detail[group_detail["source_item_name"].isin(EXPENSE_MANAGEMENT_FEE_ITEMS)]
        management_amount = _safe_float(management_rows["current_amount"].sum()) if len(management_rows) else 0.0
        cost_total = _preferred_expense_denominator(group_source, "成本费用合计")
        six_total = sum(_safe_float(value) for value in category_amounts.values())
        bridge = _expense_bridge_summary(
            cost_total,
            pd.DataFrame([{"本月金额": value} for value in category_amounts.values()]),
            management_amount,
        )
        other_or_check = (
            -_safe_float(bridge.get("check_difference"))
            if bridge.get("status") == "warning"
            else _safe_float(bridge.get("other_fee"))
        )
        if (
            abs(cost_total) < 1e-9
            and abs(six_total) < 1e-9
            and abs(management_amount) < 1e-9
            and abs(other_or_check) < 1e-9
        ):
            continue
        label = str(group.get("label") or "")
        if not group.get("is_module") and group_codes:
            label = source_name_map.get(group_codes[0], label or group_codes[0])
        raw_rows.append(
            {
                "模块/公司": label,
                **category_amounts,
                "管理费服务费": management_amount,
                "其他费用（或待核对差额）": other_or_check,
                "成本费用合计": cost_total,
            }
        )

    if not raw_rows:
        return pd.DataFrame(columns=columns)

    total_cost = sum(_safe_float(row.get("成本费用合计")) for row in raw_rows)
    view_rows: list[dict] = []
    amount_columns = columns[1:-1]
    for row in raw_rows:
        converted = {"模块/公司": row["模块/公司"]}
        for column in amount_columns:
            converted[column] = _safe_float(row.get(column)) / 10000.0
        converted["占集团成本费用比"] = _expense_ratio(row.get("成本费用合计"), total_cost)
        view_rows.append(converted)

    total_row = {"模块/公司": "合计"}
    for column in amount_columns:
        total_row[column] = sum(_safe_float(row.get(column)) for row in view_rows)
    total_row["占集团成本费用比"] = 1.0 if abs(total_cost) > 1e-9 else None
    return pd.DataFrame(view_rows + [total_row], columns=columns)


def _home_funds_warning_rows_for_period(period: str) -> pd.DataFrame:
    db_path, db_signature = _funds_warning_db_signature()
    return _home_funds_warning_rows_for_period_cached(str(period), db_path, db_signature)


@st.cache_data(show_spinner=False, ttl=120)
def _home_funds_warning_rows_for_period_cached(
    period: str,
    db_path: str,
    db_signature: tuple[tuple[str, int, int, int], ...],
) -> pd.DataFrame:
    companies = _funds_warning_company_frame()
    balances = _funds_warning_balance_metrics(period)
    costs = _funds_warning_cost_metrics(period)
    return _funds_warning_build_rows(companies, balances, costs)


def _home_funds_rows_for_scope(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    rows = _home_funds_warning_rows_for_period(period)
    if rows is None or rows.empty:
        return pd.DataFrame()
    if company_codes and "company_code" in rows.columns:
        selected = {str(code) for code in company_codes}
        return rows[rows["company_code"].astype(str).isin(selected)].copy()
    return rows.copy()


def _home_funds_summary_from_rows(rows: pd.DataFrame) -> dict:
    rows = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame()
    if rows.empty:
        return {
            "货币资金合计": 0.0,
            "其他应收款合计": 0.0,
            "其他应付款合计": 0.0,
            "可使用周转资金合计": 0.0,
            "集团资金周转系数": None,
            "纳入口径可使用周转资金合计": None,
            "纳入口径近6月平均经营成本合计": None,
            "三个月安全资金线": None,
            "安全余量": None,
            "资金紧张公司数": 0,
            "资金关注公司数": 0,
            "资金安全公司数": 0,
            "风险Top5": pd.DataFrame(columns=["公司/校区", "资金周转系数", "资金状态"]),
            "公司数": 0,
        }
    ratio_rows = _funds_warning_group_ratio_rows(rows)
    if ratio_rows.empty:
        ratio_available = None
        ratio_avg_cost = None
        safety_line = None
        safety_margin = None
    else:
        ratio_available = _funds_card_money_sum(ratio_rows, "可使用周转资金")
        ratio_avg_cost = _funds_card_money_sum(ratio_rows, "近6月平均经营成本")
        safety_line = ratio_avg_cost * 3
        safety_margin = ratio_available - safety_line
    return {
        "货币资金合计": _funds_card_money_sum(rows, "货币资金"),
        "其他应收款合计": _funds_card_money_sum(rows, "其他应收款"),
        "其他应付款合计": _funds_card_money_sum(rows, "其他应付款"),
        "可使用周转资金合计": _funds_card_money_sum(rows, "可使用周转资金"),
        "集团资金周转系数": _funds_warning_group_turnover_ratio(rows),
        "纳入口径可使用周转资金合计": ratio_available,
        "纳入口径近6月平均经营成本合计": ratio_avg_cost,
        "三个月安全资金线": safety_line,
        "安全余量": safety_margin,
        "资金紧张公司数": int((rows.get("资金状态", pd.Series(dtype=str)) == "资金紧张").sum()),
        "资金关注公司数": int((rows.get("资金状态", pd.Series(dtype=str)) == "资金关注").sum()),
        "资金安全公司数": int((rows.get("资金状态", pd.Series(dtype=str)) == "资金安全").sum()),
        "风险Top5": _funds_risk_rows(rows).head(5)[["公司/校区", "资金周转系数", "资金状态"]].copy(),
        "公司数": int(len(rows)),
    }


def _home_funds_summary_for_scope(period: str, company_codes: tuple[str, ...]) -> dict:
    db_path, db_signature = _funds_warning_db_signature()
    return _home_funds_summary_for_scope_cached(str(period), tuple(company_codes), db_path, db_signature)


@st.cache_data(show_spinner=False, ttl=120)
def _home_funds_summary_for_scope_cached(
    period: str,
    company_codes: tuple[str, ...],
    db_path: str,
    db_signature: tuple[tuple[str, int, int, int], ...],
) -> dict:
    companies = _funds_warning_company_frame()
    balances = _funds_warning_balance_metrics(period)
    costs = _funds_warning_cost_metrics(period)
    rows = _funds_warning_build_summary_rows(companies, balances, costs)
    if rows is not None and not rows.empty and company_codes and "company_code" in rows.columns:
        selected = {str(code) for code in company_codes}
        rows = rows[rows["company_code"].astype(str).isin(selected)].copy()
    return _home_funds_summary_from_rows(rows)


def _funds_card_money_sum(rows: pd.DataFrame, column: str) -> float:
    if rows is None or rows.empty or column not in rows.columns:
        return 0.0
    return _safe_float(pd.to_numeric(rows[column], errors="coerce").fillna(0.0).sum())


def _home_funds_assurance_money_text(value) -> str:
    if value is None or pd.isna(value):
        return "待接入"
    return _fmt_money_compact(value)


def _home_funds_assurance_value_class(value) -> str:
    if value is None or pd.isna(value):
        return "pending"
    if _safe_float(value) < 0:
        return "risk"
    return "good"


def _home_funds_assurance_conclusion(group_ratio) -> tuple[str, str]:
    if group_ratio is None or pd.isna(group_ratio):
        return "资金数据待接入", "pending"
    ratio = _safe_float(group_ratio)
    if ratio >= 3:
        return f"高于安全线 {ratio - 3:.1f} 个月 / 资金保障充足", "good"
    if ratio >= 2:
        return f"距离安全线差 {3 - ratio:.1f} 个月 / 需要关注", "warn"
    return f"低于紧张线 {2 - ratio:.1f} 个月 / 资金紧张", "risk"


def _render_funds_safety_panel(summary: dict | pd.DataFrame, selected_group_key: str | None = None) -> str:
    if isinstance(summary, pd.DataFrame):
        summary = _home_funds_summary_from_rows(summary)
    summary = summary if isinstance(summary, dict) else {}
    cash = _safe_float(summary.get("货币资金合计"))
    receivable = _safe_float(summary.get("其他应收款合计"))
    payable = _safe_float(summary.get("其他应付款合计"))
    available = _safe_float(summary.get("可使用周转资金合计"))
    group_ratio = summary.get("集团资金周转系数")
    avg_cost = summary.get("纳入口径近6月平均经营成本合计")
    safety_line = summary.get("三个月安全资金线")
    safety_margin = summary.get("安全余量")
    conclusion, conclusion_class = _home_funds_assurance_conclusion(group_ratio)
    components = [
        ("货币资金", cash, "good"),
        ("其他应收", receivable, "good"),
        ("其他应付", payable, "risk"),
        ("可用周转金", available, "warn" if available < 0 else "good"),
    ]
    max_value = max((abs(value) for _, value, _ in components), default=1.0)
    max_value = max(max_value, 1.0)
    body_rows = []
    for label, value, tone in components:
        width = max(abs(value) / max_value * 100, 2)
        body_rows.append(
            f"""
            <div class="home-card-mini-row">
                <div class="home-card-mini-label">{_html(label)}</div>
                <div class="home-card-mini-track">
                    <span class="home-card-mini-fill {tone}" style="--fill-width:{width:.1f}%"></span>
                </div>
                <div class="home-card-mini-value">{_html(_fmt_money_compact(value))}</div>
            </div>
            """
        )
    body = f"""
        <div class="home-card-mini">{"".join(body_rows)}</div>
        <div class="home-funds-assurance">
            <div class="home-funds-assurance-head">资金保障能力</div>
            <div class="home-funds-assurance-grid">
                <div class="home-funds-assurance-item">
                    <div class="home-funds-assurance-label">近6月月均经营成本</div>
                    <div class="home-funds-assurance-value">{_html(_home_funds_assurance_money_text(avg_cost))}</div>
                </div>
                <div class="home-funds-assurance-item">
                    <div class="home-funds-assurance-label">3个月安全资金线</div>
                    <div class="home-funds-assurance-value">{_html(_home_funds_assurance_money_text(safety_line))}</div>
                </div>
                <div class="home-funds-assurance-item">
                    <div class="home-funds-assurance-label">集团资金周转系数</div>
                    <div class="home-funds-assurance-value">{_html(_funds_warning_ratio_text(group_ratio))}</div>
                </div>
                <div class="home-funds-assurance-item">
                    <div class="home-funds-assurance-label">安全余量</div>
                    <div class="home-funds-assurance-value {_home_funds_assurance_value_class(safety_margin)}">{_html(_home_funds_assurance_money_text(safety_margin))}</div>
                </div>
            </div>
            <div class="home-funds-assurance-conclusion {conclusion_class}">{_html(conclusion)}</div>
        </div>
        <div class="home-card-footnote">资金类仅取科目余额表；其他应收/应付仅取公司往来。</div>
    """
    panel = _panel_html("资金安全", "资金构成与集团周转系数", body)
    return _home_card_group_wrap("funds_safety", selected_group_key, panel)


def _funds_risk_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame()
    risk_rows = rows[rows["资金状态"].isin(["资金紧张", "资金关注"])].copy()
    return _funds_warning_sort_rows(risk_rows, "按风险从高到低")


def _home_risk_status_class(status: str) -> str:
    if status == "资金紧张":
        return "tight"
    if status == "资金关注":
        return "watch"
    if status == "资金安全":
        return "safe"
    return "pending"


def _home_turnover_ratio_text(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _render_funds_turnover_risk_panel(summary: dict | pd.DataFrame, selected_group_key: str | None = None) -> str:
    if isinstance(summary, pd.DataFrame):
        summary = _home_funds_summary_from_rows(summary)
    summary = summary if isinstance(summary, dict) else {}
    tight_count = int(summary.get("资金紧张公司数") or 0)
    watch_count = int(summary.get("资金关注公司数") or 0)
    safe_count = int(summary.get("资金安全公司数") or 0)
    risk_rows = summary.get("风险Top5")
    risk_rows = risk_rows if isinstance(risk_rows, pd.DataFrame) else pd.DataFrame()
    if risk_rows.empty:
        risk_html = '<div class="bi-empty">当前范围暂无资金紧张或关注公司</div>'
    else:
        risk_list_rows = []
        for item in risk_rows.to_dict("records"):
            status = str(item.get("资金状态") or "")
            status_class = _home_risk_status_class(status)
            company = str(item.get("公司/校区") or "")
            risk_list_rows.append(
                f"""
                <div class="home-risk-list-row">
                    <div class="home-risk-company" title="{_html(company)}">{_html(company)}</div>
                    <div class="home-risk-ratio">{_html(_home_turnover_ratio_text(item.get("资金周转系数")))}</div>
                    <span class="home-risk-status {status_class}">{_html(status or "待接入")}</span>
                </div>
                """
            )
        risk_html = f"""
            <div class="home-risk-list">
                <div class="home-risk-list-title">
                    <span>风险优先清单</span>
                    <span style="text-align:right;">系数</span>
                    <span style="text-align:right;">状态</span>
                </div>
                {"".join(risk_list_rows)}
            </div>
        """
    body = f"""
        <div class="home-risk-summary-strip">
            <div class="home-risk-summary-item tight">资金紧张<strong>{tight_count} 家</strong></div>
            <div class="home-risk-summary-item watch">资金关注<strong>{watch_count} 家</strong></div>
            <div class="home-risk-summary-item safe">资金安全<strong>{safe_count} 家</strong></div>
        </div>
        {risk_html}
        <div class="home-card-footnote">点击查看全部公司</div>
    """
    panel = _panel_html("资金周转风险", "紧张和关注公司优先展示", body)
    return _home_card_group_wrap("funds_turnover_risk", selected_group_key, panel)


@st.cache_data(show_spinner=False, ttl=120)
def _home_company_operating_metrics_for_scope(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    source_rows = _query_operating_card_source_rows(period, list(company_codes))
    metrics = _operating_card_company_metrics_from_source(source_rows)
    columns = ["company_code", "公司", "业务板块", "收入", "成本费用合计", "净利润", "净利率"]
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=columns)
    result = metrics.copy()
    result["company_code"] = result["company_code"].astype(str)
    source_map = _home_metric_has_source_map(source_rows)
    for item_name, column in (
        (PL_REVENUE_ITEM, "收入"),
        (PL_COST_TOTAL_ITEM, "成本费用合计"),
        (PL_NET_PROFIT_ITEM, "净利润"),
    ):
        has_source = result["company_code"].apply(lambda code: (str(code), item_name) in source_map)
        result.loc[~has_source, column] = pd.NA
    result["净利率"] = result.apply(
        lambda row: None
        if _home_metric_missing(row.get("收入")) or _home_metric_missing(row.get("净利润"))
        else _safe_ratio_ui(row.get("净利润"), row.get("收入")),
        axis=1,
    )
    result = result[~result["company_code"].isin(HOME_CONSOLIDATION_RANK_EXCLUDED_CODES)].copy()
    group_lookup = _home_company_business_group_lookup()
    result["业务板块"] = result.apply(
        lambda row: group_lookup.get(str(row.get("company_code") or ""))
        or group_lookup.get(str(row.get("公司") or ""))
        or "未分组",
        axis=1,
    )
    result["_income_sort"] = pd.to_numeric(result["收入"], errors="coerce")
    return (
        result[columns + ["_income_sort"]]
        .sort_values(["_income_sort", "company_code"], ascending=[False, True], na_position="last")
        .drop(columns=["_income_sort"])
    )


def _home_company_operating_comparison_frame(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    prev_period = _period_previous_month(period)
    last_year_period = _period_same_month_last_year(period)
    current = _home_company_operating_metrics_for_scope(period, company_codes)
    columns = [
        "company_code",
        "公司",
        "业务板块",
        "本月收入",
        "上月收入",
        "去年同期收入",
        "收入环比",
        "收入同比",
        "本月净利润",
        "上月净利润",
        "去年同期净利润",
        "利润环比",
        "利润同比",
        "本月成本费用",
        "上月成本费用",
        "成本费用环比",
        "本月净利率",
        "上月净利率",
        "净利率变化",
        "收入排名",
        "利润排名",
        "收入占比",
        "利润贡献",
    ]
    if current is None or current.empty:
        return pd.DataFrame(columns=columns)
    base = current.rename(
        columns={
            "收入": "本月收入",
            "净利润": "本月净利润",
            "成本费用合计": "本月成本费用",
            "净利率": "本月净利率",
        }
    )

    def historical(period_value: str | None, prefix: str) -> pd.DataFrame:
        if not period_value:
            return pd.DataFrame(columns=["company_code", f"{prefix}收入", f"{prefix}净利润", f"{prefix}成本费用", f"{prefix}净利率"])
        frame = _home_company_operating_metrics_for_scope(period_value, company_codes)
        if frame is None or frame.empty:
            return pd.DataFrame(columns=["company_code", f"{prefix}收入", f"{prefix}净利润", f"{prefix}成本费用", f"{prefix}净利率"])
        return frame.rename(
            columns={
                "收入": f"{prefix}收入",
                "净利润": f"{prefix}净利润",
                "成本费用合计": f"{prefix}成本费用",
                "净利率": f"{prefix}净利率",
            }
        )[["company_code", f"{prefix}收入", f"{prefix}净利润", f"{prefix}成本费用", f"{prefix}净利率"]]

    merged = base.merge(historical(prev_period, "上月"), on="company_code", how="left")
    last_year = historical(last_year_period, "去年同期").rename(
        columns={
            "去年同期成本费用": "去年同期成本费用",
            "去年同期净利率": "去年同期净利率",
        }
    )
    merged = merged.merge(last_year[["company_code", "去年同期收入", "去年同期净利润"]], on="company_code", how="left")
    merged["收入环比"] = merged.apply(lambda row: _home_relative_change_value(row.get("本月收入"), row.get("上月收入")), axis=1)
    merged["收入同比"] = merged.apply(lambda row: _home_relative_change_value(row.get("本月收入"), row.get("去年同期收入")), axis=1)
    merged["利润环比"] = merged.apply(lambda row: _home_profit_change_value(row.get("本月净利润"), row.get("上月净利润")), axis=1)
    merged["利润同比"] = merged.apply(lambda row: _home_profit_change_value(row.get("本月净利润"), row.get("去年同期净利润")), axis=1)
    merged["成本费用环比"] = merged.apply(lambda row: _home_relative_change_value(row.get("本月成本费用"), row.get("上月成本费用")), axis=1)
    merged["净利率变化"] = merged.apply(
        lambda row: None
        if pd.isna(row.get("本月净利率")) or pd.isna(row.get("上月净利率"))
        else _safe_float(row.get("本月净利率")) - _safe_float(row.get("上月净利率")),
        axis=1,
    )
    merged["_income_sort"] = pd.to_numeric(merged["本月收入"], errors="coerce")
    merged["_profit_sort"] = pd.to_numeric(merged["本月净利润"], errors="coerce")
    income_order = merged.sort_values(["_income_sort", "company_code"], ascending=[False, True], na_position="last").index
    profit_order = merged.sort_values(["_profit_sort", "company_code"], ascending=[False, True], na_position="last").index
    merged["收入排名"] = pd.NA
    merged["利润排名"] = pd.NA
    for rank, idx in enumerate(income_order, start=1):
        if not pd.isna(merged.at[idx, "_income_sort"]):
            merged.at[idx, "收入排名"] = rank
    for rank, idx in enumerate(profit_order, start=1):
        if not pd.isna(merged.at[idx, "_profit_sort"]):
            merged.at[idx, "利润排名"] = rank
    total_revenue = _safe_float(pd.to_numeric(merged["本月收入"], errors="coerce").fillna(0.0).sum())
    total_abs_profit = max(_safe_float(pd.to_numeric(merged["本月净利润"], errors="coerce").fillna(0.0).abs().sum()), 1.0)
    merged["收入占比"] = merged["本月收入"].apply(lambda value: _safe_ratio_ui(value, total_revenue))
    merged["利润贡献"] = merged["本月净利润"].apply(lambda value: abs(_safe_float(value)) / total_abs_profit)
    return merged[columns]


@st.cache_data(show_spinner=False, ttl=120)
def _home_company_rank_detail_for_scope(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    detail = _home_company_operating_comparison_frame(period, company_codes)
    columns = [
        "公司",
        "业务板块",
        "经营收入",
        "收入排名",
        "经营净利润",
        "利润排名",
        "净利率",
        "收入占比",
        "利润贡献",
        "收入环比",
        "收入同比",
        "利润环比",
        "利润同比",
    ]
    if detail is None or detail.empty:
        return pd.DataFrame(columns=columns)
    result = detail.rename(
        columns={
            "本月收入": "经营收入",
            "本月净利润": "经营净利润",
            "本月净利率": "净利率",
        }
    )
    result["_income_sort"] = pd.to_numeric(result.get("经营收入"), errors="coerce")
    result = result.sort_values(["_income_sort", "company_code"], ascending=[False, True], na_position="last")
    return result[columns]


@st.cache_data(show_spinner=False, ttl=120)
def _home_company_rank_summary_for_scope(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    metrics = _home_company_operating_metrics_for_scope(period, company_codes)
    columns = ["company_code", "公司", "业务板块", "经营收入", "经营净利润", "净利率"]
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=columns)
    result = metrics.rename(
        columns={
            "收入": "经营收入",
            "净利润": "经营净利润",
        }
    )
    result["_profit_sort"] = pd.to_numeric(result.get("经营净利润"), errors="coerce")
    return (
        result[columns + ["_profit_sort"]]
        .sort_values(["_profit_sort", "company_code"], ascending=[False, True], na_position="last")
        .drop(columns=["_profit_sort"])
    )


def _home_company_rank_panel_slices(detail: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if detail is None or detail.empty:
        empty = pd.DataFrame(columns=["公司", "业务板块", "经营收入", "经营净利润", "净利率"])
        return empty, empty
    view = detail.copy()
    view["_profit_sort"] = pd.to_numeric(view.get("经营净利润"), errors="coerce")
    if "company_code" not in view.columns:
        view["company_code"] = view.get("公司", "")
    profitable = (
        view[view["_profit_sort"] > 0]
        .sort_values(["_profit_sort", "company_code", "公司"], ascending=[False, True, True], na_position="last")
        .head(5)
        .drop(columns=["_profit_sort"], errors="ignore")
    )
    bottom = (
        view.sort_values(["_profit_sort", "company_code", "公司"], ascending=[True, True, True], na_position="last")
        .head(5)
        .drop(columns=["_profit_sort"], errors="ignore")
    )
    return profitable, bottom


def _home_rank_dual_rows_html(rows_df: pd.DataFrame, max_value: float, empty_text: str) -> str:
    if rows_df is None or rows_df.empty:
        return f'<div class="bi-empty">{_html(empty_text)}</div>'
    rows: list[str] = []
    for item in rows_df.to_dict("records"):
        revenue = _safe_float(item.get("经营收入"))
        profit = _safe_float(item.get("经营净利润"))
        margin_value = item.get("净利率")
        margin_text = _fmt_percent(margin_value)
        margin_display = "暂无" if margin_text == "-" else margin_text
        margin_class = "loss" if _safe_float(margin_value) < 0 else "profit" if margin_text != "-" else ""
        revenue_width = max(abs(revenue) / max_value * 100, 2)
        profit_width = max(abs(profit) / max_value * 100, 2)
        profit_class = "loss" if profit < 0 else "profit"
        company_name = _html(item.get("公司", ""))
        rows.append(
            f"""
            <div class="home-rank-dual-row">
                <div class="home-rank-dual-name" title="{company_name}">{company_name}</div>
                <div class="home-rank-dual-bars">
                    <div class="home-rank-dual-track" title="经营收入 {_html(_fmt_money_compact(revenue))}">
                        <span class="home-rank-dual-fill" style="--fill-width:{revenue_width:.1f}%"></span>
                    </div>
                    <div class="home-rank-dual-track" title="经营净利润 {_html(_fmt_money_compact(profit))}">
                        <span class="home-rank-dual-fill {profit_class}" style="--fill-width:{profit_width:.1f}%"></span>
                    </div>
                </div>
                <div class="home-rank-dual-value">
                    <span title="经营收入 {_html(_fmt_money_compact(revenue))}">收 {_html(_fmt_money_compact(revenue))}</span>
                    <span class="{profit_class}" title="经营净利润 {_html(_fmt_money_compact(profit))}">利 {_html(_fmt_money_compact(profit))}</span>
                </div>
                <div class="home-rank-dual-margin {margin_class}" title="{_html(margin_display)}">{_html(margin_display)}</div>
            </div>
            """
        )
    return "".join(rows)


def _render_company_profit_rank_panel(detail: pd.DataFrame, selected_group_key: str | None = None) -> str:
    if detail is None or detail.empty:
        body = '<div class="bi-empty">暂无公司收入利润排行数据</div>'
    else:
        profit_top, profit_bottom = _home_company_rank_panel_slices(detail)
        view = pd.concat([profit_top, profit_bottom], ignore_index=True)
        max_value = max(
            _safe_float(pd.to_numeric(view.get("经营收入", 0), errors="coerce").fillna(0.0).abs().max()),
            _safe_float(pd.to_numeric(view.get("经营净利润", 0), errors="coerce").fillna(0.0).abs().max()),
            1.0,
        )
        body = f"""
            <div class="home-rank-table-head">公司 / 收入利润 / 金额</div>
            <div class="home-rank-two-col">
                <div class="home-rank-column">
                    <div class="home-rank-column-title">盈利前五</div>
                    <div class="home-rank-column-head"><span></span><span></span><span></span><span>净利率</span></div>
                    <div class="home-rank-dual">{_home_rank_dual_rows_html(profit_top, max_value, "暂无盈利公司")}</div>
                </div>
                <div class="home-rank-column">
                    <div class="home-rank-column-title">利润倒数前五</div>
                    <div class="home-rank-column-head"><span></span><span></span><span></span><span>净利率</span></div>
                    <div class="home-rank-dual">{_home_rank_dual_rows_html(profit_bottom, max_value, "暂无公司数据")}</div>
                </div>
            </div>
        """
    body += """
        <div class="home-card-note-grid">
            <div class="home-card-note">图形说明<strong>蓝=收入 绿/红=利润</strong></div>
            <div class="home-card-note">口径状态<strong>沿用现有口径</strong></div>
        </div>
    """
    panel = _panel_html("公司收入利润排行", "同时观察收入规模与利润贡献", body)
    return _home_card_group_wrap("company_profit_rank", selected_group_key, panel)


def _home_anomaly_row_from_comparison(row: pd.Series) -> dict | None:
    labels: list[str] = []
    degrees: list[float] = []

    def add_numeric(label: str, value, predicate) -> None:
        if value is None or isinstance(value, str):
            return
        try:
            if pd.isna(value):
                return
        except (TypeError, ValueError):
            return
        numeric = _safe_float(value)
        if predicate(numeric):
            labels.append(label)
            degrees.append(abs(numeric))

    def add_profit(label: str, value) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value in {"由盈转亏", "亏损扩大"}:
                labels.append(f"{label}（{value}）")
                degrees.append(1.0)
            return
        try:
            if pd.isna(value):
                return
        except (TypeError, ValueError):
            return
        numeric = _safe_float(value)
        if numeric < HOME_OPERATING_ANOMALY_THRESHOLDS[label]:
            labels.append(label)
            degrees.append(abs(numeric))

    add_numeric("收入同比下降", row.get("收入同比"), lambda value: value < HOME_OPERATING_ANOMALY_THRESHOLDS["收入同比下降"])
    add_numeric("收入环比下降", row.get("收入环比"), lambda value: value < HOME_OPERATING_ANOMALY_THRESHOLDS["收入环比下降"])
    add_profit("利润同比下降", row.get("利润同比"))
    add_profit("利润环比下降", row.get("利润环比"))
    add_numeric("成本费用环比上升", row.get("成本费用环比"), lambda value: value > HOME_OPERATING_ANOMALY_THRESHOLDS["成本费用环比上升"])
    add_numeric("净利率明显下滑", row.get("净利率变化"), lambda value: value < HOME_OPERATING_ANOMALY_THRESHOLDS["净利率明显下滑"])

    if not labels:
        return None
    degree = max(degrees) if degrees else 0.0
    return {
        "公司": row.get("公司"),
        "业务板块": row.get("业务板块"),
        "本月收入": row.get("本月收入"),
        "上月收入": row.get("上月收入"),
        "去年同期收入": row.get("去年同期收入"),
        "收入环比": row.get("收入环比"),
        "收入同比": row.get("收入同比"),
        "本月净利润": row.get("本月净利润"),
        "上月净利润": row.get("上月净利润"),
        "去年同期净利润": row.get("去年同期净利润"),
        "利润环比": row.get("利润环比"),
        "利润同比": row.get("利润同比"),
        "本月成本费用": row.get("本月成本费用"),
        "上月成本费用": row.get("上月成本费用"),
        "成本费用环比": row.get("成本费用环比"),
        "本月净利率": row.get("本月净利率"),
        "上月净利率": row.get("上月净利率"),
        "净利率变化": row.get("净利率变化"),
        "异常类型": "、".join(labels),
        "异常程度": degree,
        "异常程度/状态": "高风险" if any("由盈转亏" in label or "亏损扩大" in label for label in labels) else "需关注",
    }


@st.cache_data(show_spinner=False, ttl=120)
def _home_operating_anomaly_detail_for_scope(period: str, company_codes: tuple[str, ...]) -> pd.DataFrame:
    comparison = _home_company_operating_comparison_frame(period, company_codes)
    columns = [
        "公司",
        "业务板块",
        "本月收入",
        "上月收入",
        "去年同期收入",
        "收入环比",
        "收入同比",
        "本月净利润",
        "上月净利润",
        "去年同期净利润",
        "利润环比",
        "利润同比",
        "本月成本费用",
        "上月成本费用",
        "成本费用环比",
        "本月净利率",
        "上月净利率",
        "净利率变化",
        "异常类型",
        "异常程度",
        "异常程度/状态",
    ]
    if comparison is None or comparison.empty:
        return pd.DataFrame(columns=columns)
    rows = [
        anomaly
        for _, row in comparison.iterrows()
        if (anomaly := _home_anomaly_row_from_comparison(row)) is not None
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values(["异常程度", "公司"], ascending=[False, True])


def _home_operating_anomaly_counts(detail: pd.DataFrame) -> dict[str, int]:
    counts = {label: 0 for label in HOME_OPERATING_ANOMALY_THRESHOLDS}
    if detail is None or detail.empty or "异常类型" not in detail.columns:
        return counts
    labels = detail["异常类型"].fillna("").astype(str)
    for label in counts:
        counts[label] = int(labels.str.contains(label, regex=False).sum())
    return counts


@st.cache_data(show_spinner=False, ttl=120)
def _home_operating_anomaly_summary_counts_for_scope(period: str, company_codes: tuple[str, ...]) -> dict[str, int]:
    comparison = _home_company_operating_comparison_frame(period, company_codes)
    counts = {label: 0 for label in HOME_OPERATING_ANOMALY_THRESHOLDS}
    if comparison is None or comparison.empty:
        return counts
    for _, row in comparison.iterrows():
        anomaly = _home_anomaly_row_from_comparison(row)
        if anomaly is None:
            continue
        labels = str(anomaly.get("异常类型") or "")
        for label in counts:
            if label in labels:
                counts[label] += 1
    return counts


def _render_operating_anomaly_panel(detail: pd.DataFrame | dict[str, int], selected_group_key: str | None = None) -> str:
    counts = detail if isinstance(detail, dict) else _home_operating_anomaly_counts(detail)
    max_count = max(counts.values(), default=0) or 1
    rows = []
    for label, count in counts.items():
        width = max(count / max_count * 100, 2) if count else 0
        rows.append(
            f"""
            <div class="home-card-mini-row">
                <div class="home-card-mini-label" title="{_html(label)}">{_html(label)}</div>
                <div class="home-card-mini-track">
                    <span class="home-card-mini-fill risk" style="--fill-width:{width:.1f}%"></span>
                </div>
                <div class="home-card-mini-value">{count}</div>
            </div>
            """
        )
    tag_html = "".join(f'<span class="home-anomaly-tag">{_html(label)} {count}</span>' for label, count in counts.items() if count)
    body = f"""
        <div class="home-card-mini">{"".join(rows)}</div>
        <div class="home-anomaly-tags">{tag_html or '<span class="home-anomaly-tag">当前范围暂无经营波动异常</span>'}</div>
        <div class="home-card-footnote">按异常事项数统计；缺可比期间不计入异常</div>
    """
    panel = _panel_html("经营异常", "同比/环比经营波动", body)
    return _home_card_group_wrap("operating_anomaly", selected_group_key, panel)


def _render_funds_panel(balance: dict, income: dict) -> str:
    available_funds = (
        _safe_float(balance.get("cash"))
        + _safe_float(balance.get("other_receivables"))
        - _safe_float(balance.get("other_payables"))
    )
    turnover = _safe_ratio_ui(available_funds, income.get("cost_run_rate"))
    turnover_text = "-" if turnover is None else f"{turnover:,.1f} 月"
    items = [
        ("货币资金", _fmt_money_compact(balance.get("cash"))),
        ("预收账款", _fmt_money_compact(balance.get("advance_receipts"))),
        ("其他应收", _fmt_money_compact(balance.get("other_receivables"))),
        ("其他应付", _fmt_money_compact(balance.get("other_payables"))),
        ("可用周转金", _fmt_money_compact(available_funds)),
        ("资金周转", turnover_text),
    ]
    rows = "".join(
        f'<div class="bi-micro-row"><div class="label">{_html(label)}</div><div class="value">{_html(value)}</div></div>'
        for label, value in items
    )
    return _panel_html("资金安全", "现金、预收和应收应付合并看周转压力", f'<div class="bi-micro">{rows}</div>')


def _render_health_panel(completeness: dict, anomalies: list[dict], balance: dict) -> str:
    warning_count = len(anomalies or [])
    balance_gap = _safe_float(balance.get("balance_gap"))
    rows = [
        ("导入完整度", _fmt_percent(completeness.get("score"))),
        ("异常事项", f"{warning_count} 条"),
        ("资产平衡差", _fmt_money_compact(balance_gap)),
        ("覆盖公司", f"{completeness.get('expected_company_count', 0)} 家"),
    ]
    body = _progress_row_html("导入完整度", completeness.get("score"), benchmark=1.0)
    body += '<div class="bi-micro">'
    body += "".join(
        f'<div class="bi-micro-row"><div class="label">{_html(label)}</div><div class="value">{_html(value)}</div></div>'
        for label, value in rows
    )
    body += "</div>"
    return _panel_html("经营体检", "数据质量、平衡关系和异常清单集中呈现", body)


def _bar_rows_html(df: pd.DataFrame, name_col: str, value_col: str, max_rows: int, value_formatter, positive_good: bool = True) -> str:
    if df is None or len(df) == 0 or name_col not in df.columns or value_col not in df.columns:
        return '<div class="bi-empty">暂无可展示数据</div>'
    view = df.head(max_rows).copy()
    max_value = max(view[value_col].abs().max(), 1)
    rows = []
    for _, row in view.iterrows():
        value = _safe_float(row.get(value_col))
        width = max(abs(value) / max_value * 100, 2)
        tone = "positive" if (value >= 0) == positive_good else "negative"
        rows.append(
            f"""
            <div class="bi-bar-row">
                <div class="bi-bar-name" title="{_html(row.get(name_col, ""))}">{_html(row.get(name_col, ""))}</div>
                <div class="bi-bar-track"><div class="bi-bar-fill {tone}" style="width:{width:.1f}%"></div></div>
                <div class="bi-bar-value">{_html(value_formatter(value))}</div>
            </div>
            """
        )
    return "".join(rows)


def _alerts_html(anomalies: list[dict]) -> str:
    if not anomalies:
        return '<div class="bi-empty">当前范围未发现关键异常</div>'
    rows = []
    for item in anomalies[:6]:
        level = str(item.get("级别", ""))
        tone = "" if level == "预警" else "watch"
        rows.append(
            f"""
            <div class="bi-alert-item {tone}">
                <strong>{_html(item.get("项目", ""))}</strong><br>
                {_html(item.get("说明", ""))}
            </div>
            """
        )
    return f'<div class="bi-alert-list">{"".join(rows)}</div>'

# ============================================================================
# 侧边栏
# ============================================================================

NAV_MODULE_SECTIONS = {
    "经营中心": {
        "经营看板": ["首页", "全面预算", "利润表明细（原表）", "费用科目分析", "资金预警", "多维图片简报", "多期对比"],
        "经营测算": ["盈亏平衡测算"],
    },
    "数据中心": {
        "数据采集": ["数据导入", "明细表查询"],
    },
    "财务中心": {
        "基础报表": ["科目余额表", "资产负债表", "损益表", "现金流量表"],
        "管理报表": ["贡献式利润表", "多维损益表", "合并报表"],
        "报表处理": ["核算记录"],
    },
    "基础设置": {
        "基础设置": [
            "base_settings.overview",
            "base_settings.organization",
            "base_settings.company_profile",
            "base_settings.name_standard",
            "base_settings.collection_rules",
            "base_settings.import_issues",
            "base_settings.change_log",
        ],
    },
}

BASE_SETTINGS_PAGE_TABS = {
    "base_settings.overview": "首页",
    "base_settings.organization": "组织架构",
    "base_settings.company_profile": "公司档案",
    "base_settings.name_standard": "名称口径",
    "base_settings.collection_rules": "归集规则",
    "base_settings.import_issues": "导入问题池",
    "base_settings.change_log": "变更记录",
}

NAV_LABELS = {
    "首页": "驾驶舱",
    "数据导入": "数据导入",
    "明细表查询": "明细查询",
    "科目余额表": "科目余额",
    "资产负债表": "资产负债表",
    "损益表": "损益表",
    "现金流量表": "现金流量表",
    "核算记录": "核算记录",
    "多维图片简报": "图片简报",
    "贡献式利润表": "贡献式利润表",
    "多维损益表": "管理损益表",
    "多维经营汇总表": "经营汇总表",
    "利润表总览驾驶舱": "利润驾驶舱",
    "利润表明细（原表）": "经营汇总表",
    "费用科目分析": "费用分析",
    "资金预警": "资金预警",
    "全面预算": "全面预算",
    "合并报表": "合并报表",
    "多期对比": "多期对比",
    "盈亏平衡测算": "盈亏平衡测算",
    "基础设置": "基础设置",
    "base_settings.overview": "首页",
    "base_settings.organization": "组织架构",
    "base_settings.company_profile": "公司档案",
    "base_settings.name_standard": "名称口径",
    "base_settings.collection_rules": "归集规则",
    "base_settings.import_issues": "导入问题池",
    "base_settings.change_log": "变更记录",
}
NAV_PAGE_REDIRECTS = {
    "基础设置": "base_settings.overview",
    "公司层级": "base_settings.organization",
    "系统管理": "base_settings.overview",
}


def _sidebar_page_module_map(module_sections: dict[str, dict[str, list[str]]] | None = None) -> dict[str, str]:
    sections = module_sections or NAV_MODULE_SECTIONS
    return {
        item: module
        for module, grouped_pages in sections.items()
        for pages in grouped_pages.values()
        for item in pages
    }


def _normalize_sidebar_page(current: str | None) -> str:
    page = NAV_PAGE_REDIRECTS.get(str(current or "首页"), str(current or "首页"))
    return page if page in _sidebar_page_module_map() else "首页"


def _sidebar_expanded_state(
    current_page: str,
    existing: dict[str, bool] | None = None,
    module_sections: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, bool]:
    sections = module_sections or NAV_MODULE_SECTIONS
    page_module = _sidebar_page_module_map(sections)
    active_module = page_module.get(current_page, next(iter(sections)))
    existing = existing if isinstance(existing, dict) else {}
    return {
        module: bool(existing[module]) if module in existing else module == active_module
        for module in sections
    }


def _toggle_sidebar_module(expanded_modules: dict[str, bool], module_name: str) -> dict[str, bool]:
    updated = dict(expanded_modules)
    updated[module_name] = not bool(updated.get(module_name, False))
    return updated


def _set_sidebar_page(page_key: str, module_name: str) -> None:
    st.session_state.nav_choice = page_key
    st.session_state.nav_module = module_name
    if page_key in BASE_SETTINGS_PAGE_TABS:
        st.session_state["base_settings_active_tab"] = BASE_SETTINGS_PAGE_TABS[page_key]


UI_FONT_SIZE_SESSION_KEY = "ui_font_size_mode"
UI_FONT_SIZE_QUERY_KEY = "ui_font"
UI_FONT_SIZE_DEFAULT_MODE = "较大"
UI_FONT_SIZE_MODES: dict[str, float] = {
    "标准": 1.0,
    "较大": 1.12,
    "大号": 1.25,
}


def _normalize_ui_font_size_mode(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text in UI_FONT_SIZE_MODES else UI_FONT_SIZE_DEFAULT_MODE


def _current_ui_font_size_mode() -> str:
    stored_exists = UI_FONT_SIZE_SESSION_KEY in st.session_state
    stored_mode = st.session_state.get(UI_FONT_SIZE_SESSION_KEY)
    query_mode = _get_query_param(UI_FONT_SIZE_QUERY_KEY)
    if query_mode is not None:
        mode = _normalize_ui_font_size_mode(query_mode)
    elif stored_mode is not None:
        mode = _normalize_ui_font_size_mode(stored_mode)
    else:
        mode = UI_FONT_SIZE_DEFAULT_MODE
    if not stored_exists:
        st.session_state[UI_FONT_SIZE_SESSION_KEY] = mode
    elif query_mode is not None and _normalize_ui_font_size_mode(stored_mode) != mode:
        try:
            st.session_state[UI_FONT_SIZE_SESSION_KEY] = mode
        except Exception:
            pass
    return mode


def _sync_ui_font_size_query_param(mode: str) -> None:
    normalized = _normalize_ui_font_size_mode(mode)
    if not hasattr(st, "query_params"):
        return
    try:
        if normalized == UI_FONT_SIZE_DEFAULT_MODE:
            if UI_FONT_SIZE_QUERY_KEY in st.query_params:
                del st.query_params[UI_FONT_SIZE_QUERY_KEY]
        else:
            st.query_params[UI_FONT_SIZE_QUERY_KEY] = normalized
    except Exception:
        return


def _app_query_href(params: dict[str, str] | None = None) -> str:
    query_items: list[tuple[str, str]] = []
    mode = _current_ui_font_size_mode()
    if mode != UI_FONT_SIZE_DEFAULT_MODE:
        query_items.append((UI_FONT_SIZE_QUERY_KEY, mode))
    for key, value in (params or {}).items():
        if value is not None and str(value):
            query_items.append((str(key), str(value)))
    if not query_items:
        return "?"
    return "?" + "&".join(f"{quote(key)}={quote(value)}" for key, value in query_items)


def _ui_font_size_scale(mode: str | None) -> float:
    return UI_FONT_SIZE_MODES[_normalize_ui_font_size_mode(mode)]


def _render_ui_font_size_css(mode: str | None = None) -> str:
    scale = _ui_font_size_scale(mode)
    if scale == 1.0:
        return '<style id="ui-font-size-control">:root { --ui-font-scale: 1; }</style>'
    return f"""
<style id="ui-font-size-control">
    :root {{
        --ui-font-scale: {scale:.2f};
        --ui-font-body: calc(1rem * var(--ui-font-scale));
        --ui-font-small: calc(0.86rem * var(--ui-font-scale));
        --ui-font-label: calc(0.94rem * var(--ui-font-scale));
        --ui-font-title: calc(1.5rem * var(--ui-font-scale));
        --ui-font-kpi: calc(2rem * var(--ui-font-scale));
        --ui-font-table: calc(0.90rem * var(--ui-font-scale));
        --ui-font-table-head: calc(0.95rem * var(--ui-font-scale));
        --ui-font-caption: calc(0.82rem * var(--ui-font-scale));
        --ui-font-chip: calc(0.78rem * var(--ui-font-scale));
    }}

    .stApp,
    section[data-testid="stSidebar"],
    .stApp p,
    section[data-testid="stSidebar"] p,
    .stApp li,
    .stApp label,
    section[data-testid="stSidebar"] label,
    .stApp input,
    .stApp textarea,
    .stApp select,
    .stApp button,
    section[data-testid="stSidebar"] button,
    .stApp [role="combobox"],
    .stApp [data-baseweb="select"] *,
    .stApp [data-baseweb="tab"],
    .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stMarkdownContainer"] p {{
        font-size: var(--ui-font-body) !important;
        line-height: 1.42 !important;
    }}

    .page-header,
    .picture-brief-page-title {{
        font-size: var(--ui-font-title) !important;
        line-height: 1.25 !important;
    }}

    .card,
    .bi-panel,
    .home-filter-card,
    .sidebar-note,
    .stApp .stTabs,
    .stApp [data-testid="stExpander"] {{
        font-size: var(--ui-font-body) !important;
        line-height: 1.45 !important;
    }}

    .app-title {{
        font-size: calc(1.36rem * var(--ui-font-scale)) !important;
        line-height: 1.16 !important;
    }}

    .app-subtitle,
    .nav-section-title,
    .sidebar-font-control-title,
    [class*="st-key-ui_font_size_mode"] label [data-testid="stMarkdownContainer"] p {{
        font-size: var(--ui-font-small) !important;
        line-height: 1.25 !important;
    }}

    [class*="st-key-ui_font_size_mode"] label [data-testid="stMarkdownContainer"] p {{
        font-size: min(calc(0.76rem * var(--ui-font-scale)), 0.80rem) !important;
        line-height: 1.18 !important;
    }}

    [class*="st-key-nav_module_toggle_"] button,
    [class*="st-key-nav_module_toggle_"] button p {{
        font-size: calc(1rem * var(--ui-font-scale)) !important;
        line-height: 1.22 !important;
    }}

    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button,
    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button p {{
        font-size: calc(0.92rem * var(--ui-font-scale)) !important;
        line-height: 1.24 !important;
    }}

    .home-top-kpi-grid .bi-kpi-label {{
        font-size: calc(1.03rem * var(--ui-font-scale)) !important;
        line-height: 1.22 !important;
    }}

    .home-top-kpi-grid .bi-kpi-value {{
        font-size: var(--ui-font-kpi) !important;
        line-height: 1.08 !important;
    }}

    .home-top-kpi-grid .bi-kpi-delta,
    .home-top-kpi-grid .bi-kpi-trends {{
        font-size: var(--ui-font-label) !important;
        line-height: 1.28 !important;
    }}

    .bi-kpi-grid:not(.home-top-kpi-grid) .bi-kpi-label {{
        font-size: calc(0.78rem * var(--ui-font-scale)) !important;
        line-height: 1.22 !important;
    }}

    .bi-kpi-grid:not(.home-top-kpi-grid) .bi-kpi-value {{
        font-size: calc(1.42rem * var(--ui-font-scale)) !important;
        line-height: 1.15 !important;
    }}

    .bi-kpi-grid:not(.home-top-kpi-grid) .bi-kpi-delta {{
        font-size: calc(0.76rem * var(--ui-font-scale)) !important;
        line-height: 1.28 !important;
    }}

    .bi-kpi-grid:not(.home-top-kpi-grid) .bi-kpi-trends {{
        font-size: calc(0.72rem * var(--ui-font-scale)) !important;
        line-height: 1.28 !important;
    }}

    .bi-panel-title,
    .home-card-group-grid .bi-panel-title,
    .home-card-group-company-profit-rank .bi-panel-title,
    .home-detail-panel-title,
    .home-detail-modal h3 {{
        font-size: calc(1.32rem * var(--ui-font-scale)) !important;
        line-height: 1.22 !important;
    }}

    .bi-panel-subtitle,
    .home-card-footnote,
    .home-detail-panel-subtitle,
    .home-detail-unit-note {{
        font-size: var(--ui-font-label) !important;
        line-height: 1.4 !important;
    }}

    .home-card-mini-row,
    .home-card-mini-label,
    .home-card-mini-value,
    .home-card-note,
    .home-card-note strong,
    .home-budget-compare-label,
    .home-budget-compare-value,
    .home-budget-compare-gap,
    .home-budget-time-label,
    .home-budget-status-line,
    .home-expense-legend-name,
    .home-expense-legend-meta,
    .home-risk-list-row,
    .home-risk-list-title,
    .home-funds-assurance-label,
    .home-funds-assurance-value,
    .home-funds-assurance-conclusion {{
        font-size: var(--ui-font-body) !important;
        line-height: 1.35 !important;
    }}

    .home-detail-modal,
    .home-detail-modal p,
    .home-detail-table,
    .home-detail-table th,
    .home-detail-table td,
    .sticky-table-wrap table,
    .sticky-table-wrap th,
    .sticky-table-wrap td,
    .operating-summary-sticky-scroll table,
    .operating-summary-sticky-scroll th,
    .operating-summary-sticky-scroll td,
    .profit-original-table,
    .profit-original-table th,
    .profit-original-table td,
    .funds-warning-table,
    .funds-warning-table th,
    .funds-warning-table td,
    .picture-brief-table,
    .picture-brief-table th,
    .picture-brief-table td,
    .picture-brief-template-skin .template-sheet,
    .picture-brief-template-skin .template-sheet td,
    .detail-query-table,
    .detail-query-table th,
    .detail-query-table td,
    .financial-table,
    .financial-table th,
    .financial-table td,
    .stApp table,
    .stApp th,
    .stApp td {{
        font-size: var(--ui-font-table) !important;
        line-height: 1.42 !important;
    }}

    .stApp table th,
    .home-detail-table th,
    .sticky-table-wrap th,
    .operating-summary-sticky-scroll th,
    .profit-original-table th,
    .funds-warning-table th,
    .picture-brief-table th,
    .picture-brief-template-skin .template-sheet tbody tr:first-child td,
    .picture-brief-template-skin .template-sheet tr.template-header-row td,
    .picture-brief-template-skin .template-sheet tr.template-section-row td,
    .detail-query-table th,
    .financial-table th,
    .income-statement-table th,
    .budget-comparison-table th,
    .budget-drill-table th {{
        font-size: var(--ui-font-table-head) !important;
        line-height: 1.35 !important;
        font-weight: 850 !important;
    }}

    .budget-comparison-table td,
    .budget-comparison-table .budget-table-text,
    .budget-comparison-table .budget-table-num,
    .budget-comparison-table .budget-module-link,
    .budget-drill-table td,
    .budget-drill-table .budget-drill-text,
    .budget-drill-table .budget-drill-num,
    .budget-drill-table .budget-drill-center,
    .income-statement-table td,
    .funds-warning-text,
    .funds-warning-num,
    .picture-brief-table td,
    .picture-brief-template-skin .template-sheet td,
    .profit-original-table td {{
        font-size: var(--ui-font-table) !important;
        line-height: 1.42 !important;
    }}

    .budget-status-ok,
    .budget-status-lag,
    .budget-drill-status-ok,
    .budget-drill-status-lag,
    .budget-drill-status-wait,
    .funds-warning-status,
    .picture-brief-empty {{
        font-size: var(--ui-font-chip) !important;
        line-height: 1.22 !important;
    }}

    .budget-unit-note,
    .budget-drill-unit,
    .budget-bridge-note,
    .funds-warning-filter-note,
    .funds-warning-table-head span,
    .funds-warning-note,
    .profit-original-meta-sub,
    .profit-original-card-tip,
    .focus-expense-meta,
    .focus-expense-note,
    .picture-brief-note,
    .picture-brief-note li,
    .picture-brief-trend-note,
    .detail-query-limit-note,
    .base-company-node-code {{
        font-size: var(--ui-font-caption) !important;
        line-height: 1.5 !important;
    }}

    .budget-kpi-title,
    .funds-warning-card-label,
    .profit-original-card-title,
    .focus-expense-title,
    .picture-brief-kpi .label,
    .picture-brief-section h3,
    .funds-warning-table-head h3,
    .profit-original-meta-title,
    .base-company-node-title {{
        font-size: var(--ui-font-label) !important;
        line-height: 1.32 !important;
    }}

    .budget-kpi-value,
    .funds-warning-card-value,
    .focus-expense-value,
    .picture-brief-kpi .value {{
        font-size: calc(1.55rem * var(--ui-font-scale)) !important;
        line-height: 1.16 !important;
    }}

    .budget-kpi-sub,
    .budget-kpi-delta {{
        font-size: var(--ui-font-caption) !important;
        line-height: 1.45 !important;
    }}

    .stApp [data-testid="stDataFrame"],
    .stApp [data-testid="stDataFrame"] * {{
        font-size: var(--ui-font-table) !important;
    }}

    .stApp .stButton button,
    .stApp button[kind],
    .stApp [data-testid^="stBaseButton"] {{
        font-size: var(--ui-font-label) !important;
        line-height: 1.28 !important;
    }}
</style>
"""


def _render_ui_font_size_control() -> None:
    _current_ui_font_size_mode()
    st.markdown(
        '<div class="sidebar-font-control-title">显示字号</div>',
        unsafe_allow_html=True,
    )
    st.radio(
        "显示字号",
        list(UI_FONT_SIZE_MODES),
        key=UI_FONT_SIZE_SESSION_KEY,
        horizontal=True,
        label_visibility="collapsed",
    )
    _sync_ui_font_size_query_param(st.session_state.get(UI_FONT_SIZE_SESSION_KEY, UI_FONT_SIZE_DEFAULT_MODE))


def render_sidebar():
    with st.sidebar:
        st.markdown(
            """<div class="sidebar-brand"><div class="app-title">财务数据仓库</div><div class="app-subtitle">Finance Workspace</div></div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        module_sections = NAV_MODULE_SECTIONS
        labels = NAV_LABELS
        if _get_query_param("budget_drill"):
            st.session_state.nav_choice = "全面预算"
        current = _normalize_sidebar_page(st.session_state.get("nav_choice", "首页"))
        if st.session_state.get("nav_choice") != current:
            st.session_state.nav_choice = current
        page_module = _sidebar_page_module_map(module_sections)
        active_module = page_module.get(current, next(iter(module_sections)))
        if current in BASE_SETTINGS_PAGE_TABS:
            st.session_state["base_settings_active_tab"] = BASE_SETTINGS_PAGE_TABS[current]
        expanded_key = "sidebar_expanded_modules"
        if expanded_key not in st.session_state:
            legacy_open = st.session_state.get("nav_open_modules")
            legacy_state = (
                {module: module in legacy_open for module in module_sections}
                if isinstance(legacy_open, list) and legacy_open
                else {}
            )
            st.session_state[expanded_key] = _sidebar_expanded_state(current, legacy_state, module_sections)
        else:
            st.session_state[expanded_key] = _sidebar_expanded_state(
                current,
                st.session_state.get(expanded_key),
                module_sections,
            )
        st.session_state.nav_module = active_module

        for module_name, sections in module_sections.items():
            is_active_module = module_name == active_module
            is_expanded = bool(st.session_state[expanded_key].get(module_name))
            arrow = "▾" if is_expanded else "▸"
            module_icons = {"经营中心": "📊", "数据中心": "🗂", "财务中心": "💰", "基础设置": "⚙"}
            button_type = "primary" if (is_active_module or is_expanded) else "secondary"
            if st.button(
                f"{module_icons.get(module_name, '▪')}  {module_name}  {arrow}",
                key=f"nav_module_toggle_{module_name}",
                type=button_type,
                use_container_width=True,
            ):
                st.session_state[expanded_key] = _toggle_sidebar_module(
                    st.session_state[expanded_key],
                    module_name,
                )
                st.rerun()

            if not st.session_state[expanded_key].get(module_name):
                continue

            for section, items in sections.items():
                st.markdown(f'<div class="nav-section-title">{section}</div>', unsafe_allow_html=True)
                for item in items:
                    item_type = "primary" if current == item else "secondary"
                    st.button(
                        labels[item],
                        key=f"nav_{item}",
                        type=item_type,
                        use_container_width=True,
                        on_click=_set_sidebar_page,
                        args=(item, page_module.get(item, module_name)),
                    )

        _render_ui_font_size_control()
        st.markdown('<div class="sidebar-note">本地数据仓库 · SQLite</div>', unsafe_allow_html=True)
    return current

# ============================================================================
# 页面模块
# ============================================================================

HOME_DRILL_CONFIG: dict[str, dict[str, str]] = {
    "revenue": {
        "label": "本月收入",
        "title": "收入构成明细 (第二级)",
        "source": "pl_revenue",
        "item_name": "收入合计",
        "current_col": "本月收入",
        "previous_col": "上月收入",
        "root": "集团总收入",
    },
    "net_profit": {
        "label": "本月净利润",
        "title": "净利润构成明细 (第二级)",
        "source": "pl_profit",
        "item_name": "净利润",
        "current_col": "本月净利润",
        "previous_col": "上月净利润",
        "root": "集团总利润",
    },
    "net_margin": {
        "label": "净利率",
        "title": "净利率明细 (第二级)",
        "source": "pl_margin",
        "item_name": "净利率",
        "current_col": "本月净利率",
        "previous_col": "上月净利率",
        "root": "集团净利率",
    },
    "income_completion": {
        "label": "收入年度完成率",
        "title": "收入预算完成明细 (第二级)",
        "source": "budget_income",
        "item_name": "收入年度完成率",
        "current_col": "收入完成率",
        "previous_col": "时间进度",
        "root": "集团收入预算完成",
    },
    "profit_completion": {
        "label": "利润年度完成率",
        "title": "利润预算完成明细 (第二级)",
        "source": "budget_profit",
        "item_name": "利润年度完成率",
        "current_col": "利润完成率",
        "previous_col": "时间进度",
        "root": "集团利润预算完成",
    },
    "cash": {
        "label": "货币资金",
        "title": "货币资金构成明细 (第二级)",
        "source": "balance",
        "item_name": "货币资金",
        "current_col": "本月货币资金",
        "previous_col": "上月货币资金",
        "root": "集团货币资金",
    },
    "advance_receipts": {
        "label": "预收账款",
        "title": "预收账款构成明细 (第二级)",
        "source": "balance",
        "item_name": "预收账款",
        "current_col": "本月预收账款",
        "previous_col": "上月预收账款",
        "root": "集团预收账款",
    },
    "balance_gap": {
        "label": "资产负债平衡差",
        "title": "资产负债平衡差明细 (第二级)",
        "source": "balance_gap",
        "item_name": "资产负债平衡差",
        "current_col": "差额",
        "previous_col": "上月差额",
        "root": "集团资产负债平衡差",
    },
}


def _home_period_label(period: str) -> str:
    period = str(period)
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}年{period[4:6]}月"
    return period


def _previous_period(periods: list[str], current_period: str) -> str | None:
    try:
        idx = periods.index(current_period)
    except ValueError:
        return None
    next_idx = idx + 1
    if next_idx >= len(periods):
        return None
    return periods[next_idx]


def _resolve_scope_company_codes(
    scope_code: str | None,
    business_group: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
) -> list[str]:
    selected = [scope_code] if scope_code else []
    return get_report_company_scope(
        selected,
        business_group=business_group,
        business_type=business_type,
        region=region,
    )


@st.cache_data(show_spinner=False, ttl=60)
def _get_business_group_options() -> list[str]:
    df = execute_sql(
        """
        SELECT DISTINCT COALESCE(NULLIF(TRIM(business_group), ''), '未分组') AS business_group
        FROM dim_company
        ORDER BY business_group
        """
    )
    groups = df["business_group"].astype(str).tolist() if len(df) else []
    return ["不限"] + groups


@st.cache_data(show_spinner=False, ttl=60)
def _get_cached_home_dashboard(
    period: str,
    scope_code: str | None,
    company_codes: tuple[str, ...],
):
    return get_home_dashboard(period, scope_code, explicit_company_codes=list(company_codes))


def _company_filter_clause(alias: str, company_codes: list[str], params: dict, prefix: str) -> str:
    if not company_codes:
        return " AND 1 = 0"
    holders = []
    for idx, code in enumerate(company_codes):
        key = f"{prefix}_{idx}"
        params[key] = code
        holders.append(f":{key}")
    return f" AND {alias}.company_code IN ({', '.join(holders)})"


def _get_query_param(key: str) -> str | None:
    if hasattr(st, "query_params"):
        value = st.query_params.get(key)
        if value is None:
            return None
        if isinstance(value, list):
            return value[-1] if value else None
        return str(value)
    params = st.experimental_get_query_params()
    values = params.get(key, [])
    return values[-1] if values else None


def _clear_query_param(key: str) -> None:
    if hasattr(st, "query_params"):
        try:
            del st.query_params[key]
        except Exception:
            pass
        return
    params = st.experimental_get_query_params()
    if key in params:
        params.pop(key, None)
        st.experimental_set_query_params(**params)


def _set_state_value(key: str, value) -> None:
    st.session_state[key] = value


def _reset_home_filters(default_period: str, default_summary_mode: str) -> None:
    st.session_state["home_period"] = default_period
    st.session_state["home_summary_mode"] = default_summary_mode
    st.session_state["home_filter_year"] = "不限"
    st.session_state["home_filter_month"] = "不限"
    st.session_state["home_filter_group"] = "不限"
    for widget_key in [
        "home_filter_year_pills",
        "home_filter_month_pills",
        "home_filter_group_pills",
        "home_summary_mode_pills",
    ]:
        st.session_state.pop(widget_key, None)


def _toggle_home_filter_expanded() -> None:
    st.session_state.home_filter_expanded = not st.session_state.get("home_filter_expanded", False)


def _reset_workspace_filters(
    key_prefix: str,
    default_period: str,
    default_summary_mode: str,
    period_mode: str,
) -> None:
    st.session_state[f"{key_prefix}_summary_mode"] = default_summary_mode
    st.session_state[f"{key_prefix}_filter_year"] = "不限"
    st.session_state[f"{key_prefix}_filter_month"] = "不限"
    st.session_state[f"{key_prefix}_filter_group"] = "不限"
    st.session_state[f"{key_prefix}_company_units"] = []
    if period_mode == "range":
        st.session_state[f"{key_prefix}_start_period"] = default_period
        st.session_state[f"{key_prefix}_end_period"] = default_period
    else:
        st.session_state[f"{key_prefix}_period"] = default_period
    for widget_key in [
        f"{key_prefix}_filter_year_pills",
        f"{key_prefix}_filter_month_pills",
        f"{key_prefix}_filter_group_pills",
        f"{key_prefix}_summary_mode_pills",
        f"{key_prefix}_company_units",
        f"{key_prefix}_period_quick_pills",
        f"{key_prefix}_range_quick_pills",
        f"{key_prefix}_range_quick",
        f"{key_prefix}_data_status",
        f"{key_prefix}_business_type",
        f"{key_prefix}_region",
    ]:
        st.session_state.pop(widget_key, None)


def _toggle_workspace_filter_expanded(key_prefix: str) -> None:
    state_key = f"{key_prefix}_filter_expanded"
    st.session_state[state_key] = not st.session_state.get(state_key, False)


@st.cache_data(show_spinner=False, ttl=60)
def _get_workspace_company_options(
    business_group: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
) -> pd.DataFrame:
    return get_workspace_company_options(
        business_group=business_group,
        business_type=business_type,
        region=region,
    )


def _workspace_company_labels(company_options: pd.DataFrame) -> dict[str, str]:
    if company_options is None or company_options.empty:
        return {}
    labels: dict[str, str] = {}
    for row in company_options.to_dict("records"):
        code = str(row.get("code") or "")
        name = str(row.get("name") or code)
        group = str(row.get("business_group") or "")
        labels[code] = f"{code} - {name}" + (f" / {group}" if group else "")
    return labels


def _resolve_filter_company_codes(filters: dict, scope_code: str | None = None) -> list[str]:
    selected_codes = [str(code) for code in filters.get("selected_company_codes", []) if str(code)]
    if scope_code and not selected_codes:
        selected_codes = [scope_code]
    return get_report_company_scope(
        selected_codes,
        business_group=filters.get("business_group"),
        business_type=filters.get("business_type"),
        region=filters.get("region"),
    )


def _workspace_scope_label(filters: dict) -> str:
    scope_label = str(filters.get("summary_mode") or "默认公司")
    business_group = str(filters.get("business_group") or "不限")
    selected_count = len(filters.get("selected_company_codes", []) or [])
    if business_group != "不限":
        scope_label = f"{scope_label} · {business_group}"
    if selected_count:
        scope_label = f"{scope_label} · 已选{selected_count}个经营单元"
    return scope_label


def _period_button_label(period: str) -> str:
    period = str(period)
    if len(period) == 6 and period.isdigit():
        return f"{period[4:6]}月"
    return period


def _period_full_label(period: str) -> str:
    period = str(period)
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}-{period[4:6]}"
    return period


def _render_period_button_group(
    key_prefix: str,
    periods: list[str],
    period_mode: str,
    filtered_periods: list[str],
    max_buttons: int = 6,
) -> None:
    if not filtered_periods:
        return
    quick_periods = filtered_periods[:max_buttons]
    if period_mode == "range":
        range_key = f"{key_prefix}_range_quick"
        range_options = ["近3个月", "近6个月", "本年累计", "自定义区间"]
        current = st.session_state.get(range_key, "自定义区间")
        picked = st.pills(
            "快捷区间",
            range_options,
            selection_mode="single",
            default=current if current in range_options else "自定义区间",
            key=f"{key_prefix}_range_quick_pills",
            label_visibility="collapsed",
            width="content",
        )
        st.session_state[range_key] = picked or "自定义区间"
        ordered = sorted(filtered_periods)
        if picked == "近3个月":
            selected = ordered[-3:] if len(ordered) >= 3 else ordered
        elif picked == "近6个月":
            selected = ordered[-6:] if len(ordered) >= 6 else ordered
        elif picked == "本年累计":
            end_period = st.session_state.get(f"{key_prefix}_end_period", filtered_periods[0])
            year = str(end_period)[:4]
            selected = [p for p in ordered if str(p).startswith(year) and str(p) <= str(end_period)]
        else:
            selected = []
        if selected:
            st.session_state[f"{key_prefix}_start_period"] = selected[0]
            st.session_state[f"{key_prefix}_end_period"] = selected[-1]
        return

    period_key = f"{key_prefix}_period"
    label_map = {_period_button_label(p): p for p in quick_periods}
    current_period = st.session_state.get(period_key, quick_periods[0])
    current_label = _period_button_label(current_period)
    picked_label = st.pills(
        "期间快捷",
        list(label_map.keys()),
        selection_mode="single",
        default=current_label if current_label in label_map else _period_button_label(quick_periods[0]),
        key=f"{key_prefix}_period_quick_pills",
        label_visibility="collapsed",
        width="content",
    )
    if picked_label in label_map:
        st.session_state[period_key] = label_map[picked_label]


def _company_unit_summary(selected_codes: list[str], business_group: str | None) -> str:
    business_group = str(business_group or "不限")
    if not selected_codes:
        return "全部经营单元" if business_group == "不限" else f"板块：{business_group} · 全部经营单元"
    if business_group == "不限":
        return f"已选 {len(selected_codes)} 个经营单元"
    return f"板块：{business_group} · 已选 {len(selected_codes)} 个经营单元"


def _render_company_unit_picker(
    key_prefix: str,
    business_group: str,
    company_key: str,
    company_options_df: pd.DataFrame,
) -> list[str]:
    company_options = company_options_df["code"].astype(str).tolist() if len(company_options_df) else []
    company_label_map = _workspace_company_labels(company_options_df)
    selected_companies = [
        str(code) for code in st.session_state.get(company_key, [])
        if str(code) in company_options
    ]
    st.session_state[company_key] = selected_companies
    st.multiselect(
        "经营单元",
        company_options,
        key=company_key,
        format_func=lambda code: company_label_map.get(str(code), str(code)),
        placeholder="搜索公司编码或名称",
    )
    return [str(code) for code in st.session_state.get(company_key, []) if str(code)]


def _render_more_filter_panel(
    key_prefix: str,
    year_options: list[str],
    month_options: list[str],
    group_options: list[str],
    year_key: str,
    month_key: str,
    group_key: str,
    business_type_key: str,
    region_key: str,
    note: str | None = None,
) -> None:
    st.markdown('<div class="home-filter-divider"></div>', unsafe_allow_html=True)
    _render_filter_pills_row(
        f"{key_prefix}_filter_year",
        "年份",
        year_options,
        st.session_state[year_key],
        year_key,
    )
    _render_filter_pills_row(
        f"{key_prefix}_filter_month",
        "月份",
        month_options,
        st.session_state[month_key],
        month_key,
        format_func=_filter_month_format_func(key_prefix),
    )
    _render_filter_pills_row(
        f"{key_prefix}_filter_group",
        "所属板块",
        group_options,
        st.session_state[group_key],
        group_key,
    )
    status_key = f"{key_prefix}_data_status"
    if status_key not in st.session_state:
        st.session_state[status_key] = "全部"
    status_col, type_col, region_col = st.columns([1, 1, 1])
    with status_col:
        st.selectbox("数据状态", ["全部", "草稿", "已审核", "已锁定"], key=status_key)
    with type_col:
        st.selectbox("业态", ["不限"] + BUSINESS_TYPE_OPTIONS, key=business_type_key)
    with region_col:
        st.selectbox("区域", ["不限"] + REGION_OPTIONS, key=region_key)
    if note:
        st.markdown(f'<div class="home-filter-note">{_html(note)}</div>', unsafe_allow_html=True)


def _render_workspace_filter_bar(
    *,
    key_prefix: str,
    periods: list[str],
    summary_mode_options: list[str] | None = None,
    group_options: list[str] | None = None,
    title: str = "筛选条件",
    period_label: str = "统计周期",
    period_mode: str = "single",
    show_budget: bool = False,
    show_period_quick: bool = False,
    note: str | None = None,
) -> dict:
    if not periods:
        return {}

    summary_mode_options = summary_mode_options or ["默认公司"]
    group_options = group_options or ["不限"]
    year_options = ["不限"] + sorted({str(p)[:4] for p in periods if len(str(p)) >= 4}, reverse=True)
    month_options = ["不限"] + [f"{idx:02d}" for idx in range(1, 13)]
    expanded_key = f"{key_prefix}_filter_expanded"
    year_key = f"{key_prefix}_filter_year"
    month_key = f"{key_prefix}_filter_month"
    group_key = f"{key_prefix}_filter_group"
    summary_key = f"{key_prefix}_summary_mode"
    company_key = f"{key_prefix}_company_units"
    business_type_key = f"{key_prefix}_business_type"
    region_key = f"{key_prefix}_region"

    if expanded_key not in st.session_state:
        st.session_state[expanded_key] = False
    if year_key not in st.session_state or st.session_state[year_key] not in year_options:
        st.session_state[year_key] = "不限"
    if month_key not in st.session_state or st.session_state[month_key] not in month_options:
        st.session_state[month_key] = "不限"
    if group_key not in st.session_state or st.session_state[group_key] not in group_options:
        st.session_state[group_key] = "不限"
    if summary_key not in st.session_state or st.session_state[summary_key] not in summary_mode_options:
        st.session_state[summary_key] = summary_mode_options[0]
    if business_type_key not in st.session_state or st.session_state[business_type_key] not in ["不限"] + BUSINESS_TYPE_OPTIONS:
        st.session_state[business_type_key] = "不限"
    if region_key not in st.session_state or st.session_state[region_key] not in ["不限"] + REGION_OPTIONS:
        st.session_state[region_key] = "不限"

    if st.session_state.get(f"{key_prefix}_filter_year_pills") in year_options:
        st.session_state[year_key] = st.session_state[f"{key_prefix}_filter_year_pills"]
    if st.session_state.get(f"{key_prefix}_filter_month_pills") in month_options:
        st.session_state[month_key] = st.session_state[f"{key_prefix}_filter_month_pills"]
    if st.session_state.get(f"{key_prefix}_filter_group_pills") in group_options:
        st.session_state[group_key] = st.session_state[f"{key_prefix}_filter_group_pills"]

    selected_year = st.session_state[year_key]
    selected_month = st.session_state[month_key]
    company_options_df = _get_workspace_company_options(
        st.session_state[group_key],
        st.session_state[business_type_key],
        st.session_state[region_key],
    )
    filtered_periods = [
        p for p in periods
        if (selected_year == "不限" or str(p).startswith(selected_year))
        and (selected_month == "不限" or str(p)[4:6] == selected_month)
    ]
    if not filtered_periods:
        filtered_periods = periods

    default_period = filtered_periods[0]
    if period_mode == "range":
        start_key = f"{key_prefix}_start_period"
        end_key = f"{key_prefix}_end_period"
        if start_key not in st.session_state or st.session_state[start_key] not in filtered_periods:
            st.session_state[start_key] = filtered_periods[-1]
        if end_key not in st.session_state or st.session_state[end_key] not in filtered_periods:
            st.session_state[end_key] = filtered_periods[0]
    else:
        period_key = f"{key_prefix}_period"
        if period_key not in st.session_state or st.session_state[period_key] not in filtered_periods:
            st.session_state[period_key] = default_period

    with st.container(border=True, key=f"{key_prefix}_filter_card"):
        st.markdown(f'<div class="home-filter-title">{_html(title)}</div>', unsafe_allow_html=True)
        if show_period_quick:
            _render_period_button_group(key_prefix, periods, period_mode, filtered_periods, max_buttons=6)
        if show_budget:
            cols = st.columns([1.12, 0.78, 0.78, 1.55, 0.48, 0.48, 0.62])
            with cols[0]:
                st.selectbox("预算方案", ["未设置预算"], key=f"{key_prefix}_budget")
            with cols[1]:
                st.selectbox("开始", filtered_periods, key=f"{key_prefix}_start_period")
            with cols[2]:
                st.selectbox("结束", filtered_periods, key=f"{key_prefix}_end_period")
            company_col = cols[3]
            action_cols = cols[4:]
        elif period_mode == "range":
            cols = st.columns([0.82, 0.82, 1.55, 0.48, 0.48, 0.62])
            with cols[0]:
                st.selectbox("开始", filtered_periods, key=f"{key_prefix}_start_period")
            with cols[1]:
                st.selectbox("结束", filtered_periods, key=f"{key_prefix}_end_period")
            company_col = cols[2]
            action_cols = cols[3:]
        else:
            cols = st.columns([1.0, 1.55, 0.48, 0.48, 0.62])
            with cols[0]:
                st.selectbox(period_label, filtered_periods, key=f"{key_prefix}_period")
            company_col = cols[1]
            action_cols = cols[2:]

        with company_col:
            selected_companies = _render_company_unit_picker(
                key_prefix,
                st.session_state[group_key],
                company_key,
                company_options_df,
            )

        with action_cols[0]:
            st.button(
                "查询",
                key=f"{key_prefix}_filter_apply",
                type="primary",
                icon=":material/search:",
                use_container_width=True,
            )
        with action_cols[1]:
            st.button(
                "重置",
                key=f"{key_prefix}_filter_reset",
                on_click=_reset_workspace_filters,
                args=(key_prefix, periods[0], summary_mode_options[0], period_mode),
                icon=":material/restart_alt:",
                use_container_width=True,
            )
        with action_cols[2]:
            st.button(
                "收起筛选" if st.session_state[expanded_key] else "更多筛选",
                key=f"{key_prefix}_filter_toggle",
                on_click=_toggle_workspace_filter_expanded,
                args=(key_prefix,),
                icon=":material/tune:",
                use_container_width=True,
            )

        if st.session_state[expanded_key]:
            _render_more_filter_panel(
                key_prefix,
                year_options,
                month_options,
                group_options,
                year_key,
                month_key,
                group_key,
                business_type_key,
                region_key,
                note,
            )
    result = {
        "summary_mode": st.session_state[summary_key],
        "business_group": st.session_state[group_key],
        "business_type": st.session_state[business_type_key],
        "region": st.session_state[region_key],
        "selected_company_codes": list(st.session_state.get(company_key, [])),
        "filtered_periods": filtered_periods,
    }
    if period_mode == "range":
        start_period = st.session_state[f"{key_prefix}_start_period"]
        end_period = st.session_state[f"{key_prefix}_end_period"]
        ordered_periods = sorted(filtered_periods)
        start_idx = ordered_periods.index(start_period) if start_period in ordered_periods else 0
        end_idx = ordered_periods.index(end_period) if end_period in ordered_periods else len(ordered_periods) - 1
        if start_idx > end_idx:
            start_period, end_period = end_period, start_period
        result.update({"start_period": start_period, "end_period": end_period})
    else:
        result["period"] = st.session_state[f"{key_prefix}_period"]
    return result


def _render_filter_chip_row(
    row_key: str,
    label: str,
    options: list[str],
    selected: str,
    session_key: str,
    max_per_row: int = 10,
) -> None:
    if not options:
        return

    label_col, chips_col = st.columns([1, 16], gap="small")
    with label_col:
        st.markdown(f'<div class="quick-filter-label">{_html(label)}：</div>', unsafe_allow_html=True)

    with chips_col:
        rows = ceil(len(options) / max_per_row)
        for row_idx in range(rows):
            chunk = options[row_idx * max_per_row:(row_idx + 1) * max_per_row]
            cols = st.columns(len(chunk), gap="small")
            for idx, option in enumerate(chunk):
                button_type = "primary" if option == selected else "secondary"
                cols[idx].button(
                    option,
                    key=f"{row_key}_{row_idx}_{idx}_{option}",
                    type=button_type,
                    on_click=_set_state_value,
                    args=(session_key, option),
                    use_container_width=True,
                )


def _render_filter_pills_row(
    row_key: str,
    label: str,
    options: list[str],
    selected: str,
    session_key: str,
    format_func=None,
) -> None:
    if not options:
        return

    current_value = selected if selected in options else options[0]
    widget_key = f"{row_key}_pills"

    if widget_key in st.session_state and st.session_state[widget_key] not in options:
        st.session_state[widget_key] = current_value
    if widget_key not in st.session_state:
        st.session_state[widget_key] = current_value

    is_operating_filter = row_key.startswith(("profit_original_filter_", "operating_summary_filter_"))
    label_weight = 1.45 if is_operating_filter else 1.05
    pills_weight = 16.25 if is_operating_filter else 16.65
    column_gap = "medium" if is_operating_filter else "small"
    label_class = "quick-filter-label operating-filter-label" if is_operating_filter else "quick-filter-label"

    label_col, pills_col = st.columns([label_weight, pills_weight], gap=column_gap)
    with label_col:
        st.markdown(f'<div class="{label_class}">{_html(label)}：</div>', unsafe_allow_html=True)
    with pills_col:
        picked = st.pills(
            label,
            options,
            selection_mode="single",
            default=current_value,
            format_func=format_func,
            key=widget_key,
            label_visibility="collapsed",
            width="content",
        )
        st.session_state[session_key] = picked if picked in options else current_value


def _filter_month_display_label(value) -> str:
    text = str(value)
    if text == "不限":
        return text
    if text.isdigit():
        month = int(text)
        if 1 <= month <= 12:
            return f"{month}月"
    return text


def _filter_month_format_func(key_prefix: str):
    if key_prefix in {"profit_original", "operating_summary"}:
        return _filter_month_display_label
    return None


def _query_pl_metric_by_company(
    period: str,
    company_codes: list[str],
) -> pd.DataFrame:
    params = {"period": period}
    company_sql = _company_filter_clause("d", company_codes, params, "drill_pl")
    rows = execute_sql(
        f"""
        SELECT
            d.id,
            d.company_code AS 公司编码,
            d.company_code AS company_code,
            d.item_code,
            d.item_name,
            d.amount,
            COALESCE(c.short_name, c.name, d.company_code) AS 公司,
            COALESCE(NULLIF(TRIM(dim.business_group), ''), '未分组') AS 业务板块
        FROM pl_detail d
        LEFT JOIN companies c ON d.company_code = c.code
        LEFT JOIN dim_company dim ON CAST(dim.company_id AS TEXT) = CAST(d.company_code AS TEXT)
        WHERE d.period = :period
          AND d.item_name IN (:revenue_item, :profit_item)
          {company_sql}
        """,
        {**params, "revenue_item": PL_REVENUE_ITEM, "profit_item": PL_NET_PROFIT_ITEM},
    )
    if rows.empty:
        return pd.DataFrame(columns=["公司编码", "公司", "业务板块", "收入", "净利润"])
    preferred = preferred_pl_detail_rows(rows)
    if preferred.empty:
        return pd.DataFrame(columns=["公司编码", "公司", "业务板块", "收入", "净利润"])
    preferred["_amount"] = pd.to_numeric(preferred.get("amount"), errors="coerce").fillna(0.0)
    pivot = (
        preferred.pivot_table(
            index=["公司编码", "公司", "业务板块"],
            columns="item_name",
            values="_amount",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in (PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM):
        if column not in pivot.columns:
            pivot[column] = 0.0
    return pivot.rename(columns={PL_REVENUE_ITEM: "收入", PL_NET_PROFIT_ITEM: "净利润"})


def _query_operating_card_group_by_company(
    period: str,
    company_codes: list[str],
    detail_group_key: str | None = None,
) -> pd.DataFrame:
    source_rows = _query_operating_card_source_rows(period, company_codes)
    company_metrics = _operating_card_company_metrics_from_source(source_rows)
    if detail_group_key:
        return _operating_card_group_company_detail(company_metrics, company_codes, detail_group_key)
    adjustments = _operating_card_internal_fee_split(source_rows, company_metrics, company_codes)
    return _operating_card_group_summary(company_metrics, company_codes, adjustments)


@st.cache_data(show_spinner=False, ttl=120)
def _home_operating_summary_for_scope(period: str, company_codes: tuple[str, ...]) -> dict:
    group_df = _query_operating_card_group_by_company(period, list(company_codes))
    if group_df.empty:
        return {"revenue": 0.0, "cost_total": 0.0, "net_profit": 0.0, "net_margin": None}
    total_df = group_df[group_df["模块组/公司"].astype(str) == "合计"]
    total = total_df.iloc[0] if not total_df.empty else group_df.iloc[-1]
    revenue = _safe_float(total.get("经营收入"))
    cost_total = _safe_float(total.get("成本费用合计"))
    net_profit = _safe_float(total.get("经营净利润"))
    return {
        "revenue": revenue,
        "cost_total": cost_total,
        "net_profit": net_profit,
        "net_margin": _safe_ratio_ui(net_profit, revenue),
    }


def _query_operating_card_company_metrics(
    period: str,
    company_codes: list[str],
) -> pd.DataFrame:
    source_rows = _query_operating_card_source_rows(period, company_codes)
    return _operating_card_company_metrics_from_source(source_rows)


def _query_operating_card_fee_reconciliation(period: str, company_codes: list[str]) -> pd.DataFrame:
    source_rows = _query_operating_card_source_rows(period, company_codes)
    metrics = _operating_card_company_metrics_from_source(source_rows)
    split = _operating_card_internal_fee_split(source_rows, metrics, company_codes)
    reconciliation = split.get("reconciliation")
    if isinstance(reconciliation, pd.DataFrame):
        return reconciliation
    return pd.DataFrame(
        columns=[
            "company_code",
            "公司",
            "主营业务收入",
            "实表管理费服务费",
            "理论非学科服务费",
            "理论10204服务费",
            "推定101管理中心收费",
            "未匹配10204服务费",
            "差额",
        ]
    )


def _query_operating_card_source_rows(period: str, company_codes: list[str]) -> pd.DataFrame:
    params = {"period": period}
    company_sql = _company_filter_clause("d", company_codes, params, "card_operating")
    return execute_sql(
        f"""
        SELECT
            d.id,
            d.company_code AS 公司编码,
            d.company_code AS company_code,
            d.item_code,
            d.item_name,
            d.amount,
            COALESCE(NULLIF(TRIM(c.name), ''), d.company_code) AS 公司
        FROM pl_detail d
        LEFT JOIN companies c ON d.company_code = c.code
        WHERE d.period = :period
          AND d.item_name IN (:revenue_item, :profit_item, :cost_item, :main_revenue_item, :management_fee_item)
          {company_sql}
        """,
        {
            **params,
            "revenue_item": PL_REVENUE_ITEM,
            "profit_item": PL_NET_PROFIT_ITEM,
            "cost_item": PL_COST_TOTAL_ITEM,
            "main_revenue_item": HOME_MAIN_REVENUE_ITEM,
            "management_fee_item": HOME_MANAGEMENT_FEE_ITEM,
        },
    )


def _operating_card_company_metrics_from_source(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ["company_code", "公司", "收入", "成本费用合计", "净利润", "净利率"]
    if rows is None or rows.empty:
        return pd.DataFrame(columns=columns)
    target_rows = rows[rows["item_name"].astype(str).isin({PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM, PL_COST_TOTAL_ITEM})].copy()
    preferred = preferred_pl_detail_rows(target_rows)
    if preferred.empty:
        return pd.DataFrame(columns=columns)
    preferred["_amount"] = pd.to_numeric(preferred.get("amount"), errors="coerce").fillna(0.0)
    pivot = (
        preferred.pivot_table(
            index=["company_code", "公司"],
            columns="item_name",
            values="_amount",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in (PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM, PL_COST_TOTAL_ITEM):
        if column not in pivot.columns:
            pivot[column] = 0.0
    result = pivot.rename(
        columns={
            PL_REVENUE_ITEM: "收入",
            PL_COST_TOTAL_ITEM: "成本费用合计",
            PL_NET_PROFIT_ITEM: "净利润",
        }
    )
    result["净利率"] = result.apply(lambda row: _safe_ratio_ui(row["净利润"], row["收入"]), axis=1)
    return result[columns].sort_values("收入", ascending=False)


def _operating_card_main_revenue_map(source_rows: pd.DataFrame) -> dict[str, float]:
    if source_rows is None or source_rows.empty:
        return {}
    main_rows = source_rows[source_rows["item_name"].astype(str).str.strip() == HOME_MAIN_REVENUE_ITEM].copy()
    if main_rows.empty:
        return {}
    main_rows["_amount"] = pd.to_numeric(main_rows.get("amount"), errors="coerce").fillna(0.0)
    return {
        str(code): _safe_float(amount)
        for code, amount in main_rows.groupby(main_rows["company_code"].astype(str))["_amount"].sum().to_dict().items()
    }


def _operating_card_management_fee_map(source_rows: pd.DataFrame) -> dict[str, float]:
    if source_rows is None or source_rows.empty:
        return {}
    fee_rows = source_rows[source_rows["item_name"].astype(str).str.strip() == HOME_MANAGEMENT_FEE_ITEM].copy()
    if fee_rows.empty:
        return {}
    fee_rows["_amount"] = pd.to_numeric(fee_rows.get("amount"), errors="coerce").fillna(0.0)
    return {
        str(code): _safe_float(amount)
        for code, amount in fee_rows.groupby(fee_rows["company_code"].astype(str))["_amount"].sum().to_dict().items()
    }


def _operating_card_quality_participant_codes(company_codes: list[str], main_revenue: dict[str, float]) -> list[str]:
    scope_set = {str(code) for code in company_codes if str(code)}
    quality_codes = set(get_consolidation_company_codes("10101"))
    excluded = {HOME_NON_SUBJECT_CENTER_CODE, HOME_SONGSHANHU_CODE}
    return [
        code
        for code in sorted(scope_set & quality_codes)
        if code not in excluded and abs(_safe_float(main_revenue.get(code))) > 1e-9
    ]


def _operating_card_non_subject_allocation(
    center_cost: float,
    participant_codes: list[str],
    main_revenue: dict[str, float],
) -> dict[str, float]:
    denominator = sum(_safe_float(main_revenue.get(code)) for code in participant_codes)
    if abs(denominator) <= 1e-9 or abs(center_cost) <= 1e-9:
        return {code: 0.0 for code in participant_codes}
    return {
        code: _safe_float(center_cost) * _safe_float(main_revenue.get(code)) / denominator
        for code in participant_codes
    }


def _operating_card_proportional_match(amounts: dict[str, float], receiver_income: float) -> tuple[dict[str, float], dict[str, float]]:
    positive_total = sum(max(_safe_float(amount), 0.0) for amount in amounts.values())
    receiver_income = max(_safe_float(receiver_income), 0.0)
    if positive_total <= 1e-9 or receiver_income <= 1e-9:
        return {code: 0.0 for code in amounts}, {code: _safe_float(amount) for code, amount in amounts.items()}
    ratio = min(receiver_income / positive_total, 1.0)
    matched = {code: _safe_float(amount) * ratio for code, amount in amounts.items()}
    unmatched = {code: _safe_float(amounts.get(code)) - _safe_float(matched.get(code)) for code in amounts}
    return matched, unmatched


def _operating_card_eryu_internal_fee_split(
    company_codes: list[str],
    actual_fee: dict[str, float],
    main_revenue: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    scope_set = {str(code) for code in company_codes if str(code)}
    if HOME_ERYU_CENTER_CODE not in scope_set:
        payers = {
            code: _safe_float(amount)
            for code, amount in actual_fee.items()
            if code in (set(get_consolidation_company_codes(HOME_ERYU_CENTER_CODE)) - {HOME_ERYU_CENTER_CODE}) & scope_set
        }
        return {code: 0.0 for code in payers}, payers
    eryu_codes = set(get_consolidation_company_codes(HOME_ERYU_CENTER_CODE))
    payer_amounts = {
        code: _safe_float(amount)
        for code, amount in actual_fee.items()
        if code in scope_set and code in eryu_codes and code != HOME_ERYU_CENTER_CODE and abs(_safe_float(amount)) > 1e-9
    }
    return _operating_card_proportional_match(payer_amounts, _safe_float(main_revenue.get(HOME_ERYU_CENTER_CODE)))


def _operating_card_internal_fee_split(
    source_rows: pd.DataFrame,
    metrics: pd.DataFrame,
    company_codes: list[str],
    *,
    assign_residual_to_management: bool = True,
) -> dict:
    scope_set = {str(code) for code in company_codes if str(code)}
    main_revenue = _operating_card_main_revenue_map(source_rows)
    actual_fee = _operating_card_management_fee_map(source_rows)
    center_rows = metrics[metrics["company_code"].astype(str) == HOME_NON_SUBJECT_CENTER_CODE] if metrics is not None and not metrics.empty else pd.DataFrame()
    center_cost = _safe_float(center_rows["成本费用合计"].iloc[0]) if len(center_rows) else 0.0
    participant_codes = _operating_card_quality_participant_codes(company_codes, main_revenue)
    non_subject_fee = _operating_card_non_subject_allocation(center_cost, participant_codes, main_revenue)
    eryu_fee, unmatched_eryu_fee = _operating_card_eryu_internal_fee_split(company_codes, actual_fee, main_revenue)
    non_subject_unmatched_fee: dict[str, float] = {}
    if not assign_residual_to_management:
        for code in participant_codes:
            residual = (
                _safe_float(actual_fee.get(code))
                - _safe_float(non_subject_fee.get(code))
            )
            if residual > 1e-9:
                non_subject_unmatched_fee[code] = residual
    payer_codes = sorted(
        (set(actual_fee) | set(non_subject_fee) | set(non_subject_unmatched_fee) | set(eryu_fee) | set(unmatched_eryu_fee))
        & scope_set
    )
    management_fee = {
        code: _safe_float(actual_fee.get(code))
        - _safe_float(non_subject_fee.get(code))
        - _safe_float(non_subject_unmatched_fee.get(code))
        - _safe_float(eryu_fee.get(code))
        - _safe_float(unmatched_eryu_fee.get(code))
        for code in payer_codes
    }
    reconciliation = []
    name_map = _operating_card_company_name_map(payer_codes)
    for code in payer_codes:
        actual = _safe_float(actual_fee.get(code))
        non_subject = _safe_float(non_subject_fee.get(code))
        non_subject_unmatched = _safe_float(non_subject_unmatched_fee.get(code))
        eryu = _safe_float(eryu_fee.get(code))
        unmatched_eryu = _safe_float(unmatched_eryu_fee.get(code))
        management = _safe_float(management_fee.get(code))
        reconciliation.append(
            {
                "company_code": code,
                "公司": name_map.get(code, code),
                "主营业务收入": _safe_float(main_revenue.get(code)),
                "实表管理费服务费": actual,
                "理论非学科服务费": non_subject,
                "未匹配非学科服务费": non_subject_unmatched,
                "理论10204服务费": eryu,
                "推定101管理中心收费": management,
                "未匹配10204服务费": unmatched_eryu,
                "差额": actual - non_subject - non_subject_unmatched - eryu - management - unmatched_eryu,
            }
        )
    return {
        "main_revenue": main_revenue,
        "participants": participant_codes,
        "non_subject_fee": non_subject_fee,
        "non_subject_unmatched_fee": non_subject_unmatched_fee,
        "eryu_fee": eryu_fee,
        "unmatched_eryu_fee": unmatched_eryu_fee,
        "management_fee": management_fee,
        "actual_fee": actual_fee,
        "reconciliation": pd.DataFrame(reconciliation),
    }


def _operating_card_revenue_cost_adjustment(
    adjustments: dict | None,
    codes: list[str],
    *,
    include_non_subject: bool,
    include_management: bool,
    include_eryu: bool = False,
) -> float:
    if not adjustments:
        return 0.0
    code_set = {str(code) for code in codes}
    total = 0.0
    if include_non_subject:
        non_subject = adjustments.get("non_subject_fee") or {}
        total += sum(_safe_float(non_subject.get(code)) for code in code_set)
    if include_management:
        management = adjustments.get("management_fee") or {}
        total += sum(_safe_float(management.get(code)) for code in code_set)
    if include_eryu:
        eryu = adjustments.get("eryu_fee") or {}
        total += sum(_safe_float(eryu.get(code)) for code in code_set)
    return _safe_float(total)


def _operating_card_company_name_map(company_codes: list[str]) -> dict[str, str]:
    codes = [str(code) for code in company_codes if str(code)]
    if not codes:
        return {}
    params = {f"code_{idx}": code for idx, code in enumerate(codes)}
    placeholders = ", ".join(f":code_{idx}" for idx in range(len(codes)))
    rows = execute_sql(
        f"""
        SELECT CAST(code AS TEXT) AS code, COALESCE(NULLIF(TRIM(name), ''), CAST(code AS TEXT)) AS name
        FROM companies
        WHERE CAST(code AS TEXT) IN ({placeholders})
        """,
        params,
    )
    return {str(row["code"]): str(row["name"]) for row in rows.to_dict("records")}


def _operating_card_group_scopes(company_codes: list[str]) -> list[dict]:
    scope_codes = [str(code) for code in company_codes if str(code)]
    scope_set = set(scope_codes)
    assigned: set[str] = set()
    groups: list[dict] = []
    for group in HOME_OPERATING_CARD_GROUPS:
        group_code = group["code"]
        candidate_codes = [group_code] if group_code == "101" else get_consolidation_company_codes(group_code)
        codes = [code for code in candidate_codes if code in scope_set and code not in assigned]
        if codes:
            groups.append({**group, "codes": codes, "is_module": True})
            assigned.update(codes)
    name_map = _operating_card_company_name_map([code for code in scope_codes if code not in assigned])
    for code in scope_codes:
        if code in assigned:
            continue
        groups.append(
            {
                "key": f"company:{code}",
                "label": name_map.get(code, code),
                "code": code,
                "codes": [code],
                "is_module": False,
            }
        )
        assigned.add(code)
    return groups


def _operating_card_group_label(group_key: str | None) -> str | None:
    if not group_key:
        return None
    for group in HOME_OPERATING_CARD_GROUPS:
        if group["key"] == group_key:
            return group["label"]
    return None


def _operating_card_group_link(group_key: str, label: str) -> str:
    href = _app_query_href({"home_group": "operating_summary", "home_group_view": str(group_key)})
    return (
        f'<a class="home-detail-row-link" href="{_html(href)}" '
        f'target="_top" title="查看{_html(label)}公司明细">{_html(label)}</a>'
    )


def _operating_card_aggregate_rows(metrics: pd.DataFrame, label: str, revenue_cost_adjustment: float = 0.0) -> dict:
    revenue = _safe_float(pd.to_numeric(metrics.get("收入"), errors="coerce").fillna(0.0).sum()) if len(metrics) else 0.0
    cost_total = _safe_float(pd.to_numeric(metrics.get("成本费用合计"), errors="coerce").fillna(0.0).sum()) if len(metrics) else 0.0
    net_profit = _safe_float(pd.to_numeric(metrics.get("净利润"), errors="coerce").fillna(0.0).sum()) if len(metrics) else 0.0
    revenue -= _safe_float(revenue_cost_adjustment)
    cost_total -= _safe_float(revenue_cost_adjustment)
    return {
        "模块组/公司": label,
        "经营收入": revenue,
        "成本费用合计": cost_total,
        "经营净利润": net_profit,
        "净利率": _safe_ratio_ui(net_profit, revenue),
    }


def _operating_card_group_summary(metrics: pd.DataFrame, company_codes: list[str], adjustments: dict | None = None) -> pd.DataFrame:
    columns = ["模块组/公司", "经营收入", "成本费用合计", "经营净利润", "净利率"]
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=columns)
    metric_codes = set(metrics["company_code"].astype(str).tolist())
    rows: list[dict] = []
    assigned_metric_codes: set[str] = set()
    for group in _operating_card_group_scopes(company_codes):
        group_codes = [code for code in group["codes"] if code in metric_codes and code not in assigned_metric_codes]
        if not group_codes:
            continue
        group_metrics = metrics[metrics["company_code"].astype(str).isin(group_codes)]
        label = group["label"]
        display_label = _operating_card_group_link(group["key"], label) if group.get("is_module") else label
        group_adjustment = _operating_card_revenue_cost_adjustment(
            adjustments,
            group_codes,
            include_non_subject=group.get("key") == "quality" and HOME_NON_SUBJECT_CENTER_CODE in group_codes,
            include_management=False,
            include_eryu=group.get("key") == "eryu" and HOME_ERYU_CENTER_CODE in group_codes,
        )
        rows.append(_operating_card_aggregate_rows(group_metrics, display_label, group_adjustment))
        assigned_metric_codes.update(group_codes)
    if not rows:
        return pd.DataFrame(columns=columns)
    total_metrics = metrics[metrics["company_code"].astype(str).isin(assigned_metric_codes)]
    total_adjustment = _operating_card_revenue_cost_adjustment(
        adjustments,
        list(assigned_metric_codes),
        include_non_subject=HOME_NON_SUBJECT_CENTER_CODE in assigned_metric_codes,
        include_management=HOME_MANAGEMENT_CENTER_CODE in assigned_metric_codes,
        include_eryu=HOME_ERYU_CENTER_CODE in assigned_metric_codes,
    )
    total = _operating_card_aggregate_rows(total_metrics, "合计", total_adjustment)
    result = pd.DataFrame(rows + [total], columns=columns)
    return result


def _operating_card_assigned_metric_codes(metrics: pd.DataFrame, company_codes: list[str]) -> list[str]:
    if metrics is None or metrics.empty:
        return []
    metric_codes = set(metrics["company_code"].astype(str).tolist())
    assigned: list[str] = []
    seen: set[str] = set()
    for group in _operating_card_group_scopes(company_codes):
        for code in group["codes"]:
            code = str(code)
            if code in metric_codes and code not in seen:
                assigned.append(code)
                seen.add(code)
    return assigned


def _operating_card_bridge_summary(period: str, company_codes: list[str]) -> dict:
    source_rows = _query_operating_card_source_rows(period, company_codes)
    metrics = _operating_card_company_metrics_from_source(source_rows)
    adjustments = _operating_card_internal_fee_split(source_rows, metrics, company_codes)
    assigned_codes = _operating_card_assigned_metric_codes(metrics, company_codes)
    metric_rows = metrics[metrics["company_code"].astype(str).isin(assigned_codes)] if len(assigned_codes) else pd.DataFrame()
    raw_revenue = _safe_float(pd.to_numeric(metric_rows.get("收入"), errors="coerce").fillna(0.0).sum()) if len(metric_rows) else 0.0
    raw_cost = _safe_float(pd.to_numeric(metric_rows.get("成本费用合计"), errors="coerce").fillna(0.0).sum()) if len(metric_rows) else 0.0
    raw_profit = _safe_float(pd.to_numeric(metric_rows.get("净利润"), errors="coerce").fillna(0.0).sum()) if len(metric_rows) else 0.0
    assigned_set = set(assigned_codes)
    non_subject = _operating_card_revenue_cost_adjustment(
        adjustments,
        assigned_codes,
        include_non_subject=HOME_NON_SUBJECT_CENTER_CODE in assigned_set,
        include_management=False,
    )
    management = _operating_card_revenue_cost_adjustment(
        adjustments,
        assigned_codes,
        include_non_subject=False,
        include_management=HOME_MANAGEMENT_CENTER_CODE in assigned_set,
    )
    eryu = _operating_card_revenue_cost_adjustment(
        adjustments,
        assigned_codes,
        include_non_subject=False,
        include_management=False,
        include_eryu=HOME_ERYU_CENTER_CODE in assigned_set,
    )
    other = 0.0
    total_adjustment = _safe_float(non_subject + management + eryu + other)
    unmatched_eryu = sum(_safe_float((adjustments.get("unmatched_eryu_fee") or {}).get(code)) for code in assigned_codes)
    reconciliation = adjustments.get("reconciliation")
    transactions: list[dict] = []
    if isinstance(reconciliation, pd.DataFrame) and not reconciliation.empty:
        for item in reconciliation.to_dict("records"):
            code = str(item.get("company_code") or "")
            non_subject_amount = _safe_float(item.get("理论非学科服务费"))
            management_amount = _safe_float(item.get("推定101管理中心收费"))
            eryu_amount = _safe_float(item.get("理论10204服务费"))
            if abs(non_subject_amount) > 1e-9:
                transactions.append(
                    {
                        "付款公司": code,
                        "收款公司": HOME_NON_SUBJECT_CENTER_CODE,
                        "科目": HOME_MANAGEMENT_FEE_ITEM,
                        "金额": non_subject_amount,
                        "层级": "素质中心/集团",
                        "类别": "1010101非学科服务费",
                    }
                )
            if abs(management_amount) > 1e-9:
                transactions.append(
                    {
                        "付款公司": code,
                        "收款公司": HOME_MANAGEMENT_CENTER_CODE,
                        "科目": HOME_MANAGEMENT_FEE_ITEM,
                        "金额": management_amount,
                        "层级": "集团",
                        "类别": "101管理中心服务费",
                    }
                )
            if abs(eryu_amount) > 1e-9:
                transactions.append(
                    {
                        "付款公司": code,
                        "收款公司": HOME_ERYU_CENTER_CODE,
                        "科目": HOME_MANAGEMENT_FEE_ITEM,
                        "金额": eryu_amount,
                        "层级": "尔遇书馆/集团",
                        "类别": "10204尔遇书馆服务费",
                    }
                )
    return {
        "raw_revenue": raw_revenue,
        "raw_cost_total": raw_cost,
        "raw_net_profit": raw_profit,
        "non_subject_fee": _safe_float(non_subject),
        "management_fee": _safe_float(management),
        "eryu_fee": _safe_float(eryu),
        "other_fee": _safe_float(other),
        "total_adjustment": total_adjustment,
        "consolidated_revenue": _safe_float(raw_revenue - total_adjustment),
        "consolidated_cost_total": _safe_float(raw_cost - total_adjustment),
        "consolidated_net_profit": raw_profit,
        "unmatched_eryu_fee": _safe_float(unmatched_eryu),
        "transactions": transactions,
        "reconciliation": reconciliation if isinstance(reconciliation, pd.DataFrame) else pd.DataFrame(),
    }


@st.cache_data(show_spinner=False, ttl=120)
def _operating_card_bridge_summary_cached(period: str, company_codes: tuple[str, ...]) -> dict:
    return _operating_card_bridge_summary(period, list(company_codes))


def _home_company_rank_bridge_html(period: str, company_codes: list[str]) -> str:
    bridge = _operating_card_bridge_summary_cached(period, tuple(company_codes))
    total_adjustment = _safe_float(bridge.get("total_adjustment"))
    pieces = [
        f'<span class="home-detail-bridge-pill">单体收入合计 <strong>{_html(_fmt_money_compact(bridge.get("raw_revenue")))}</strong></span>',
        f'<span class="home-detail-bridge-pill">减内部抵消 <strong>{_html(_fmt_money_compact(total_adjustment))}</strong></span>',
        f'<span class="home-detail-bridge-pill">合并收入 <strong>{_html(_fmt_money_compact(bridge.get("consolidated_revenue")))}</strong></span>',
        f'<span class="home-detail-bridge-pill">1010101 <strong>{_html(_fmt_money_compact(bridge.get("non_subject_fee")))}</strong></span>',
        f'<span class="home-detail-bridge-pill">101 <strong>{_html(_fmt_money_compact(bridge.get("management_fee")))}</strong></span>',
        f'<span class="home-detail-bridge-pill">10204 <strong>{_html(_fmt_money_compact(bridge.get("eryu_fee")))}</strong></span>',
    ]
    if abs(_safe_float(bridge.get("unmatched_eryu_fee"))) > 1e-6:
        pieces.append(
            f'<span class="home-detail-bridge-pill">10204未匹配 <strong>{_html(_fmt_money_compact(bridge.get("unmatched_eryu_fee")))}</strong></span>'
        )
    return (
        '<div class="home-detail-bridge-note">'
        '<span>公司排行采用单体原始口径；经营汇总采用合并口径，已抵消内部管理服务费。</span>'
        + "".join(pieces)
        + "</div>"
    )


def _operating_card_group_company_detail(
    metrics: pd.DataFrame,
    company_codes: list[str],
    detail_group_key: str,
) -> pd.DataFrame:
    columns = ["公司", "经营收入", "成本费用合计", "经营净利润", "净利率"]
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=columns)
    selected_group = None
    for group in _operating_card_group_scopes(company_codes):
        if group.get("is_module") and group["key"] == detail_group_key:
            selected_group = group
            break
    if not selected_group:
        return pd.DataFrame(columns=columns)
    group_codes = set(selected_group["codes"])
    detail = metrics[metrics["company_code"].astype(str).isin(group_codes)].copy()
    if detail.empty:
        return pd.DataFrame(columns=columns)
    detail = detail.rename(columns={"收入": "经营收入", "净利润": "经营净利润"})
    return detail[columns].sort_values("经营收入", ascending=False)


def _query_balance_metric_by_company(
    period: str,
    company_codes: list[str],
) -> pd.DataFrame:
    params = {"period": period}
    company_sql = _company_filter_clause("b", company_codes, params, "drill_balance")
    return execute_sql(
        f"""
        SELECT
            b.company_code AS 公司编码,
            COALESCE(c.short_name, c.name, b.company_code) AS 公司,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS 业务板块,
            SUM(CASE WHEN b.item_name = '货币资金' THEN b.ending_balance ELSE 0 END) AS 货币资金,
            SUM(CASE WHEN b.item_name = '预收账款' THEN b.ending_balance ELSE 0 END) AS 预收账款,
            SUM(CASE WHEN b.item_name = '资产总计' THEN b.ending_balance ELSE 0 END) AS 资产总计,
            SUM(CASE WHEN b.item_name = '负债和所有者权益（或股东权益）总计' THEN b.ending_balance ELSE 0 END) AS 负债权益总计
        FROM balance_sheet b
        LEFT JOIN companies c ON b.company_code = c.code
        LEFT JOIN dim_company d ON CAST(d.company_id AS TEXT) = CAST(b.company_code AS TEXT)
        WHERE b.period = :period
          AND b.item_name IN ('货币资金', '预收账款', '资产总计', '负债和所有者权益（或股东权益）总计')
          {company_sql}
        GROUP BY b.company_code, COALESCE(c.short_name, c.name, b.company_code),
                 COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组')
        """,
        params,
    )


def _relative_change_value(current, previous):
    previous_value = _safe_float(previous)
    if abs(previous_value) < 1e-9:
        return None
    return (_safe_float(current) - previous_value) / abs(previous_value)


def _load_metric_drilldown(
    metric_key: str,
    period: str,
    prev_period: str | None,
    company_codes: list[str],
) -> pd.DataFrame:
    cfg = HOME_DRILL_CONFIG.get(metric_key)
    if not cfg:
        return pd.DataFrame()
    source = cfg.get("source")
    if source in {"pl_revenue", "pl_profit", "pl_margin"}:
        current = _query_pl_metric_by_company(period, company_codes)
        previous = _query_pl_metric_by_company(prev_period, company_codes) if prev_period else pd.DataFrame()
        last_year_period = _period_same_month_last_year(period)
        last_year = _query_pl_metric_by_company(last_year_period, company_codes) if last_year_period else pd.DataFrame()
        merged = current.merge(
            previous[["公司编码", "收入", "净利润"]].rename(
                columns={"收入": "上月收入", "净利润": "上月净利润"}
            ) if len(previous) else pd.DataFrame(columns=["公司编码", "上月收入", "上月净利润"]),
            on="公司编码",
            how="left",
        ).merge(
            last_year[["公司编码", "收入", "净利润"]].rename(
                columns={"收入": "去年收入", "净利润": "去年净利润"}
            ) if len(last_year) else pd.DataFrame(columns=["公司编码", "去年收入", "去年净利润"]),
            on="公司编码",
            how="left",
        )
        merged["净利率"] = merged.apply(lambda row: _safe_ratio_ui(row["净利润"], row["收入"]), axis=1)
        merged["上月净利率"] = merged.apply(lambda row: _safe_ratio_ui(row.get("上月净利润"), row.get("上月收入")), axis=1)
        if source == "pl_revenue":
            total = _safe_float(merged["收入"].sum())
            merged["收入占比"] = merged["收入"].apply(lambda value: _safe_ratio_ui(value, total))
            merged["环比"] = merged.apply(lambda row: _relative_change_value(row["收入"], row.get("上月收入")), axis=1)
            merged["同比"] = merged.apply(lambda row: _relative_change_value(row["收入"], row.get("去年收入")), axis=1)
            return merged[["公司", "业务板块", "收入", "收入占比", "环比", "同比"]].sort_values("收入", ascending=False)
        if source == "pl_profit":
            total_abs = max(_safe_float(merged["净利润"].abs().sum()), 1.0)
            merged["利润贡献"] = merged["净利润"].abs() / total_abs
            merged["环比"] = merged.apply(lambda row: _relative_change_value(row["净利润"], row.get("上月净利润")), axis=1)
            merged["同比"] = merged.apply(lambda row: _relative_change_value(row["净利润"], row.get("去年净利润")), axis=1)
            merged["是否亏损"] = merged["净利润"].apply(lambda value: "亏损" if _safe_float(value) < 0 else "盈利")
            return merged[["公司", "业务板块", "净利润", "利润贡献", "环比", "同比", "是否亏损"]].sort_values("净利润")
        merged["净利率变化"] = merged["净利率"] - merged["上月净利率"]
        return merged[["公司", "收入", "净利润", "净利率", "上月净利率", "净利率变化"]].sort_values("净利率")

    if source in {"balance", "balance_gap"}:
        current = _query_balance_metric_by_company(period, company_codes)
        previous = _query_balance_metric_by_company(prev_period, company_codes) if prev_period else pd.DataFrame()
        last_year_period = _period_same_month_last_year(period)
        last_year = _query_balance_metric_by_company(last_year_period, company_codes) if last_year_period else pd.DataFrame()
        if len(current) == 0:
            return current
        current["差额"] = current["资产总计"] - current["负债权益总计"]
        if source == "balance":
            item_name = cfg["item_name"]
            previous_value_col = f"上月{item_name}"
            last_year_value_col = f"去年{item_name}"
            previous_view = (
                previous[["公司编码", item_name]].rename(columns={item_name: previous_value_col})
                if len(previous)
                else pd.DataFrame(columns=["公司编码", previous_value_col])
            )
            last_year_view = (
                last_year[["公司编码", item_name]].rename(columns={item_name: last_year_value_col})
                if len(last_year)
                else pd.DataFrame(columns=["公司编码", last_year_value_col])
            )
            merged = current.merge(previous_view, on="公司编码", how="left").merge(last_year_view, on="公司编码", how="left")
            total = _safe_float(merged[item_name].sum())
            merged["占比"] = merged[item_name].apply(lambda value: _safe_ratio_ui(value, total))
            merged["环比"] = merged.apply(lambda row: _relative_change_value(row[item_name], row.get(previous_value_col)), axis=1)
            merged["同比"] = merged.apply(lambda row: _relative_change_value(row[item_name], row.get(last_year_value_col)), axis=1)
            return merged[["公司", item_name, "占比", "环比", "同比"]].sort_values(item_name, ascending=False)
        current["是否平衡"] = current["差额"].apply(lambda value: "平衡" if abs(_safe_float(value)) <= 1 else "不平衡")
        return current[["公司", "资产总计", "负债权益总计", "差额", "是否平衡"]].sort_values("差额")

    if source in {"budget_income", "budget_profit"}:
        plan_df = read_budget_plan()
        actual_df = load_budget_actuals(period)
        _, detail_df = build_budget_completion_data(plan_df, actual_df, str(period)[4:6])
        if detail_df.empty:
            return detail_df
        if source == "budget_income":
            columns = ["模块", "公司", "年度收入预算", "累计收入实际", "收入完成率", "时间进度", "收入偏离", "状态"]
            view = detail_df.rename(
                columns={
                    "module": "模块",
                    "公司名称": "公司",
                    "unit_name": "公司",
                    "收入预算": "年度收入预算",
                    "income_budget": "年度收入预算",
                    "收入实际": "累计收入实际",
                    "income_actual": "累计收入实际",
                    "income_completion": "收入完成率",
                    "收入进度差": "收入偏离",
                    "progress": "时间进度",
                    "income_gap": "收入偏离",
                    "status": "状态",
                }
            )
        else:
            columns = ["模块", "公司", "年度利润预算", "累计利润实际", "利润完成率", "时间进度", "利润偏离", "状态"]
            view = detail_df.rename(
                columns={
                    "module": "模块",
                    "公司名称": "公司",
                    "unit_name": "公司",
                    "利润预算": "年度利润预算",
                    "profit_budget": "年度利润预算",
                    "利润实际": "累计利润实际",
                    "profit_actual": "累计利润实际",
                    "profit_completion": "利润完成率",
                    "利润进度差": "利润偏离",
                    "progress": "时间进度",
                    "profit_gap": "利润偏离",
                    "status": "状态",
                }
            )
        if "时间进度" not in view.columns:
            view["时间进度"] = budget_time_progress(str(period)[4:6])
        return view[[column for column in columns if column in view.columns]]

    return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def _home_budget_summary_from_budget_dashboard(period: str) -> dict:
    period_year = str(period)[:4]
    budget_year = _home_budget_plan_year()
    if budget_year and period_year != budget_year:
        return {}
    plan_df = read_budget_plan()
    actual_df = load_budget_actuals(period)
    overview_df, detail_df = build_budget_completion_data(plan_df, actual_df, str(period)[4:6])
    return _home_budget_summary_payload(period, overview_df, detail_df)


def _home_budget_summary_payload(period: str, overview_df: pd.DataFrame, detail_df: pd.DataFrame) -> dict:
    if overview_df.empty:
        return {}
    total_row = overview_df[overview_df["模块名称"] == "合计"]
    if total_row.empty:
        total_row = overview_df.head(1)
    row = total_row.iloc[0].to_dict()
    return {
        "year": str(period)[:4],
        "income_target": _safe_float(row.get("收入预算")),
        "profit_target": _safe_float(row.get("利润预算")),
        "income_actual_ytd": _safe_float(row.get("收入实际")),
        "profit_actual_ytd": _safe_float(row.get("利润实际")),
        "income_completion": row.get("收入完成率"),
        "profit_completion": row.get("利润完成率"),
        "theory_completion": row.get("时间进度"),
        "progress": overview_df,
        "detail": detail_df,
    }


def _budget_plan_for_actual_scope(plan_df: pd.DataFrame, actual_df: pd.DataFrame) -> pd.DataFrame:
    if plan_df is None or plan_df.empty or actual_df is None or actual_df.empty:
        return _budget_empty_plan_frame()
    modules = {
        _budget_text(value)
        for value in actual_df.get("module", pd.Series(dtype=str)).tolist()
        if _budget_text(value)
    }
    unit_pairs = {
        (_budget_text(row.get("module")), _budget_text(row.get("unit_name")))
        for row in actual_df.to_dict("records")
        if _budget_text(row.get("module")) and _budget_text(row.get("unit_name"))
    }
    rows = []
    for row in plan_df.to_dict("records"):
        module = _budget_text(row.get("module"))
        if not module or module == "合计" or module not in modules:
            continue
        level = _budget_text(row.get("budget_level"))
        unit_name = _budget_text(row.get("unit_name"))
        if level == "module" or (module, unit_name) in unit_pairs:
            rows.append(row)
    if not rows:
        return _budget_empty_plan_frame()
    return pd.DataFrame(rows, columns=_budget_empty_plan_frame().columns)


def _home_budget_summary_for_scope(period: str, company_codes: list[str] | None) -> dict:
    selected_codes = {str(code) for code in (company_codes or []) if str(code)}
    if not selected_codes:
        return _home_budget_summary_from_budget_dashboard(period)
    plan_df = read_budget_plan()
    actual_df = load_budget_actuals(period)
    if actual_df.empty or "company_code" not in actual_df.columns:
        return _home_budget_summary_payload(
            period,
            *build_budget_completion_data(_budget_empty_plan_frame(), _budget_empty_actual_frame(), str(period)[4:6]),
        )
    actual_codes = {str(code) for code in actual_df["company_code"].dropna().astype(str).tolist() if str(code)}
    if actual_codes and actual_codes.issubset(selected_codes):
        return _home_budget_summary_from_budget_dashboard(period)
    scoped_actual = actual_df[actual_df["company_code"].astype(str).isin(selected_codes)].copy()
    if scoped_actual.empty:
        return _home_budget_summary_payload(
            period,
            *build_budget_completion_data(_budget_empty_plan_frame(), _budget_empty_actual_frame(), str(period)[4:6]),
        )
    scoped_actual = _budget_attach_internal_adjustments(scoped_actual, period)
    scoped_plan = _budget_plan_for_actual_scope(plan_df, scoped_actual)
    overview_df, detail_df = build_budget_completion_data(scoped_plan, scoped_actual, str(period)[4:6])
    if not overview_df.empty and "合计" not in set(overview_df["模块名称"].astype(str)):
        overview_df = pd.concat([overview_df, pd.DataFrame([_budget_total_row(overview_df)])], ignore_index=True)
    return _home_budget_summary_payload(period, overview_df, detail_df)


def _home_budget_plan_year() -> str | None:
    for text_value in (BUDGET_VERSION, BUDGET_WORKBOOK_PATH.name):
        match = re.search(r"(20\d{2})", str(text_value))
        if match:
            return match.group(1)
    return None


def _period_previous_month(period: str) -> str | None:
    period = str(period)
    if len(period) != 6 or not period.isdigit():
        return None
    year = int(period[:4])
    month = int(period[4:6])
    if month <= 1:
        return f"{year - 1}12"
    return f"{year}{month - 1:02d}"


def _period_same_month_last_year(period: str) -> str | None:
    period = str(period)
    if len(period) != 6 or not period.isdigit():
        return None
    return f"{int(period[:4]) - 1}{period[4:6]}"


def _home_budget_completion_comparisons(period: str, key: str) -> dict:
    current = _home_budget_summary_from_budget_dashboard(period)
    previous_period = _period_previous_month(period)
    last_year_period = _period_same_month_last_year(period)
    previous = _home_budget_summary_from_budget_dashboard(previous_period) if previous_period else {}
    last_year = _home_budget_summary_from_budget_dashboard(last_year_period) if last_year_period else {}
    current_value = current.get(key)

    def diff(other: dict) -> float | None:
        if not current or not other or current.get("year") != other.get("year"):
            return None
        other_value = other.get(key)
        if current_value is None or other_value is None:
            return None
        return _safe_float(current_value) - _safe_float(other_value)

    return {
        "同比": {"value": diff(last_year), "mode": "point"},
        "环比": {"value": diff(previous), "mode": "point"},
    }


def _apply_home_budget_kpi_overrides(dashboard: dict, period: str) -> dict:
    budget = _home_budget_summary_from_budget_dashboard(period)
    if not budget:
        return dashboard
    dashboard["budget"] = budget
    for kpi in dashboard.get("kpis", []):
        label = kpi.get("label")
        if label == "本月收入":
            kpi["delta"] = budget.get("income_completion")
        elif label == "收入年度完成率":
            kpi["value"] = budget.get("income_completion")
            kpi["comparisons"] = _home_budget_completion_comparisons(period, "income_completion")
        elif label == "利润年度完成率":
            kpi["value"] = budget.get("profit_completion")
            kpi["comparisons"] = _home_budget_completion_comparisons(period, "profit_completion")
    return dashboard


def _metric_drilldown_formatters(df: pd.DataFrame) -> dict:
    formatters = {}
    for column in df.columns:
        text = str(column)
        if any(token in text for token in ("率", "占比", "偏离", "进度", "贡献", "环比", "同比", "变化")):
            formatters[column] = lambda value: "-" if pd.isna(value) else f"{float(value) * 100:.2f}%"
        elif any(token in text for token in ("收入", "利润", "资金", "账款", "预算", "实际", "资产", "负债", "差额")):
            formatters[column] = lambda value: "-" if pd.isna(value) else f"{float(value):,.2f}"
    return formatters


def _metric_drilldown_highlight(row: pd.Series) -> list[str]:
    styles = []
    for value in row:
        try:
            number = float(value)
        except (TypeError, ValueError):
            styles.append("")
            continue
        styles.append("color:#b42318;font-weight:700;" if number < 0 else "")
    return styles


def _metric_drilldown_layer_type(metric_key: str) -> str:
    return "modal"


@st.cache_data(show_spinner=False, ttl=120)
def _load_metric_drilldown_cached(
    metric_key: str,
    period: str,
    prev_period: str | None,
    company_codes: tuple[str, ...],
) -> pd.DataFrame:
    return _load_metric_drilldown(metric_key, period, prev_period, list(company_codes))


def _metric_drilldown_value_html(column: str, value) -> tuple[str, str]:
    text = str(column)
    class_names: list[str] = []
    if text == "模块组/公司" and isinstance(value, str) and value.lstrip().startswith("<a "):
        return value, " ".join(class_names)
    number_value: float | None = None
    try:
        if value is not None and not pd.isna(value):
            number_value = float(value)
    except (TypeError, ValueError):
        number_value = None

    if number_value is not None and "排名" in text:
        class_names.append("num")
        display = f"{int(number_value):,}"
    elif number_value is not None and (
        any(token in text for token in ("率", "占比", "偏离", "进度", "贡献", "环比", "同比", "变化"))
        or text in {"占成本费用比", "占收入比"}
        or text.endswith("比")
    ):
        class_names.append("num")
        display = f"{number_value * 100:.2f}%"
    elif number_value is not None and (
        any(token in text for token in ("收入", "利润", "资金", "账款", "预算", "实际", "资产", "负债", "差额", "金额", "成本", "费用"))
        or text == "资金周转系数"
    ):
        class_names.append("num")
        display = f"{number_value:,.2f}"
    elif number_value is not None:
        display = f"{number_value:,.2f}"
    else:
        empty_display = "暂无" if any(token in text for token in ("环比", "同比")) else "-"
        try:
            is_missing = value is None or bool(pd.isna(value))
        except (TypeError, ValueError):
            is_missing = value is None
        display = empty_display if is_missing else str(value)

    if number_value is not None and number_value < 0:
        class_names.append("neg")
    elif number_value is not None and number_value > 0 and any(token in text for token in ("环比", "同比", "变化")):
        class_names.append("pos")
    if text in {"是否亏损", "是否平衡", "状态", "资金状态"} or text.endswith("状态"):
        label = str(display)
        if any(token in label for token in ("亏损", "不平衡", "滞后", "风险")):
            display = f'<span class="home-detail-tag-risk">{_html(label)}</span>'
        elif any(token in label for token in ("关注", "待")):
            display = f'<span class="home-detail-tag-warn">{_html(label)}</span>'
        elif label and label != "-":
            display = f'<span class="home-detail-tag-good">{_html(label)}</span>'
        return display, " ".join(class_names)
    if text == "异常类型":
        labels = [item.strip() for item in str(display).split("、") if item.strip() and item.strip() != "-"]
        if labels:
            display = "".join(f'<span class="home-detail-tag-risk">{_html(label)}</span>' for label in labels)
            return display, " ".join(class_names)
    return _html(display), " ".join(class_names)


def _metric_drilldown_column_class(column: str) -> str:
    text = str(column)
    if text in {"公司", "经营单位", "模块组/公司", "模块/公司"}:
        return "col-company"
    if text in {"业务板块", "模块", "费用类别", "明细类型"}:
        return "col-text"
    if text in {"是否亏损", "是否平衡", "状态", "资金状态"} or text.endswith("状态"):
        return "col-status"
    if "排名" in text:
        return "col-number"
    if (
        any(token in text for token in ("率", "占比", "偏离", "进度", "贡献", "环比", "同比", "变化"))
        or text in {"占成本费用比", "占收入比"}
        or text.endswith("比")
    ):
        return "col-percent"
    if any(token in text for token in ("收入", "利润", "资金", "账款", "预算", "实际", "资产", "负债", "差额", "金额", "成本", "费用")) or text == "资金周转系数":
        return "col-number"
    return "col-text"


def _metric_drilldown_sort_href(
    metric_key: str,
    column: str,
    current_sort: str | None,
    current_order: str | None,
    key_param: str = "drill_metric",
    sort_param: str = "drill_sort",
    order_param: str = "drill_order",
    extra_params: dict[str, str] | None = None,
) -> tuple[str, str, str]:
    is_active = str(column) == str(current_sort or "")
    active_order = str(current_order or "asc").lower()
    next_order = "desc" if is_active and active_order == "asc" else "asc"
    if is_active:
        icon = "▲" if active_order == "asc" else "▼"
        icon_class = "home-detail-sort active"
    else:
        icon = "⇅"
        icon_class = "home-detail-sort"
    params = {
        key_param: str(metric_key),
        sort_param: str(column),
        order_param: next_order,
    }
    for param_key, param_value in (extra_params or {}).items():
        if param_value is not None and str(param_value):
            params[str(param_key)] = str(param_value)
    href = _app_query_href(params)
    return href, icon, icon_class


def _sort_metric_drilldown_df(df: pd.DataFrame, sort_column: str | None, sort_order: str | None) -> pd.DataFrame:
    if df is None or df.empty or not sort_column or sort_column not in df.columns:
        return df
    ascending = str(sort_order or "asc").lower() != "desc"
    sorted_df = df.copy()
    first_column = sorted_df.columns[0] if len(sorted_df.columns) else None
    total_mask = pd.Series(False, index=sorted_df.index)
    if first_column is not None:
        total_mask = sorted_df[first_column].astype(str).str.replace(r"<[^>]+>", "", regex=True).str.strip().isin({"合计"})
        sortable_df = sorted_df[~total_mask].copy()
        total_df = sorted_df[total_mask].copy()
    else:
        sortable_df = sorted_df
        total_df = sorted_df.iloc[0:0].copy()
    column_class = _metric_drilldown_column_class(str(sort_column))
    if column_class in {"col-number", "col-percent"}:
        numeric_values = pd.to_numeric(sortable_df[sort_column], errors="coerce")
        sortable_df["_sort_value"] = numeric_values
        sorted_result = sortable_df.sort_values("_sort_value", ascending=ascending, na_position="last").drop(columns=["_sort_value"])
    else:
        sorted_result = sortable_df.sort_values(
            sort_column,
            ascending=ascending,
            na_position="last",
            key=lambda series: series.astype(str).str.replace(r"<[^>]+>", "", regex=True),
        )
    if not total_df.empty:
        sorted_result = pd.concat([sorted_result, total_df], ignore_index=True)
    return sorted_result


def _metric_drilldown_colgroup_html(columns: list[str]) -> str:
    weights: dict[str, float] = {}
    for column in columns:
        class_name = _metric_drilldown_column_class(column)
        if class_name == "col-company":
            weights[column] = 1.2
        else:
            weights[column] = 1.0
    total_weight = sum(weights.values()) or 1.0
    col_tags = []
    for column in columns:
        class_name = _metric_drilldown_column_class(column)
        width = weights[column] / total_weight * 100.0
        col_tags.append(f'<col class="{_html(class_name)}" style="width:{width:.2f}%">')
    return f"<colgroup>{''.join(col_tags)}</colgroup>"


def _metric_drilldown_table_html(
    df: pd.DataFrame,
    metric_key: str = "",
    current_sort: str | None = None,
    current_order: str | None = None,
    key_param: str = "drill_metric",
    sort_param: str = "drill_sort",
    order_param: str = "drill_order",
    extra_params: dict[str, str] | None = None,
) -> str:
    if df is None or df.empty:
        return '<div class="home-detail-empty">当前范围暂无可展示的下钻数据。</div>'
    view_df = _sort_metric_drilldown_df(df, current_sort, current_order)
    table_min_width = max(920, int(ceil(len(view_df.columns) * 145 * 1.05)))
    headers = []
    for column in view_df.columns:
        col_class = _metric_drilldown_column_class(str(column))
        href, icon, icon_class = _metric_drilldown_sort_href(
            metric_key,
            str(column),
            current_sort,
            current_order,
            key_param=key_param,
            sort_param=sort_param,
            order_param=order_param,
            extra_params=extra_params,
        )
        headers.append(
            f'<th class="{_html(col_class)}">'
            f'<a class="home-detail-sort-link" href="{_html(href)}" target="_top" title="按{_html(str(column))}排序">'
            f'<span class="home-detail-sort-label">{_html(column)}</span><span class="{_html(icon_class)}">{_html(icon)}</span>'
            '</a></th>'
        )
    rows = []
    for record in view_df.to_dict("records"):
        cells = []
        for column in view_df.columns:
            col_class = _metric_drilldown_column_class(str(column))
            value_html, class_name = _metric_drilldown_value_html(str(column), record.get(column))
            class_values = " ".join(value for value in [col_class, class_name] if value)
            class_attr = f' class="{_html(class_values)}"' if class_values else ""
            title_attr = f' title="{_html(str(record.get(column)))}"' if record.get(column) is not None else ""
            cells.append(f"<td{class_attr}{title_attr}>{value_html}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
        <div class="home-detail-table-wrap">
            <table class="home-detail-table" style="--home-detail-column-count:{len(view_df.columns)}; min-width:max(100%, {table_min_width}px);">
                {_metric_drilldown_colgroup_html([str(column) for column in view_df.columns])}
                <thead><tr>{''.join(headers)}</tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </div>
    """


def _render_metric_drilldown_layer(
    metric_key: str,
    period: str,
    prev_period: str | None,
    scope_label: str,
    company_codes: list[str],
) -> None:
    cfg = HOME_DRILL_CONFIG.get(metric_key)
    if not cfg:
        return
    layer_class = f"home-detail-{_metric_drilldown_layer_type(metric_key)}"
    drill_df = _load_metric_drilldown_cached(metric_key, period, prev_period, tuple(company_codes))
    sort_column = _get_query_param("drill_sort")
    sort_order = _get_query_param("drill_order")
    if sort_order not in {"asc", "desc"}:
        sort_order = None
    table_html = _metric_drilldown_table_html(
        drill_df,
        metric_key=metric_key,
        current_sort=sort_column,
        current_order=sort_order,
    )
    detail_html = (
        f'<div class="home-detail-overlay">'
        f'<div class="home-detail-layer {layer_class}">'
        '<div class="home-detail-header">'
        '<div>'
        f'<div class="home-detail-title">{_html(cfg["label"])}下钻</div>'
        '<div class="home-detail-subtitle">'
        f'{_html(_home_period_label(period))} · 范围：{_html(scope_label)} · 点击后按需加载明细'
        '</div>'
        '</div>'
        f'<a class="home-detail-close" href="{_html(_app_query_href())}" target="_top" title="关闭详情层" aria-label="关闭详情层">×</a>'
        '</div>'
        f'<div class="home-detail-body">{table_html}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(detail_html, unsafe_allow_html=True)


def _load_home_card_group_detail(
    group_key: str,
    period: str,
    company_codes: list[str],
    detail_key: str | None = None,
) -> pd.DataFrame:
    if group_key == "budget_execution":
        budget = _home_budget_summary_for_scope(period, company_codes)
        overview_df = budget.get("progress") if isinstance(budget, dict) else pd.DataFrame()
        view = _budget_comparison_table_view(overview_df)
        if view.empty:
            return view
        return view[
            [
                "经营单位",
                "收入预算",
                "收入实际",
                "收入完成率",
                "利润预算",
                "利润实际",
                "利润完成率",
                "时间进度",
                "进度判断",
            ]
        ]
    if group_key == "operating_summary":
        return _query_operating_card_group_by_company(period, company_codes, detail_key)
    if group_key == "expense_analysis":
        return _home_expense_analysis_detail_for_scope(period, company_codes)
    if group_key == "funds_safety":
        rows = _home_funds_rows_for_scope(period, tuple(company_codes))
        if rows is None or rows.empty:
            return pd.DataFrame(
                columns=[
                    "公司",
                    "货币资金",
                    "其他应收款",
                    "其他应付款",
                    "可使用周转资金",
                    "近6月平均经营成本",
                    "资金周转系数",
                    "资金状态",
                ]
            )
        return rows.rename(columns={"公司/校区": "公司"})[
            [
                "公司",
                "货币资金",
                "其他应收款",
                "其他应付款",
                "可使用周转资金",
                "近6月平均经营成本",
                "资金周转系数",
                "资金状态",
            ]
        ]
    if group_key == "funds_turnover_risk":
        rows = _funds_risk_rows(_home_funds_rows_for_scope(period, tuple(company_codes)))
        if rows is None or rows.empty:
            return pd.DataFrame(
                columns=[
                    "公司",
                    "可使用周转资金",
                    "近6月平均经营成本",
                    "资金周转系数",
                    "资金状态",
                ]
            )
        return rows.rename(columns={"公司/校区": "公司"})[
            [
                "公司",
                "可使用周转资金",
                "近6月平均经营成本",
                "资金周转系数",
                "资金状态",
            ]
        ]
    if group_key == "company_profit_rank":
        return _home_company_rank_detail_for_scope(period, tuple(company_codes))
    if group_key == "operating_anomaly":
        return _home_operating_anomaly_detail_for_scope(period, tuple(company_codes))
    return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=120)
def _load_home_card_group_detail_cached(
    group_key: str,
    period: str,
    company_codes: tuple[str, ...],
    detail_key: str | None = None,
) -> pd.DataFrame:
    return _load_home_card_group_detail(group_key, period, list(company_codes), detail_key)


def _render_home_card_group_layer(
    group_key: str,
    period: str,
    scope_label: str,
    company_codes: list[str],
) -> None:
    cfg = HOME_CARD_GROUP_CONFIG.get(group_key)
    if not cfg:
        return
    detail_key = _get_query_param("home_group_view") if group_key == "operating_summary" else None
    detail_label = _operating_card_group_label(detail_key) if group_key == "operating_summary" else None
    if detail_key and not detail_label:
        detail_key = None
    detail_df = _load_home_card_group_detail_cached(group_key, period, tuple(company_codes), detail_key)
    sort_column = _get_query_param("home_group_sort")
    sort_order = _get_query_param("home_group_order")
    if sort_order not in {"asc", "desc"}:
        sort_order = None
    table_html = _metric_drilldown_table_html(
        detail_df,
        metric_key=group_key,
        current_sort=sort_column,
        current_order=sort_order,
        key_param="home_group",
        sort_param="home_group_sort",
        order_param="home_group_order",
        extra_params={"home_group_view": detail_key} if detail_label else None,
    )
    back_html = (
        f'<a class="home-detail-back" href="{_html(_app_query_href({"home_group": "operating_summary"}))}" target="_top">← 返回模块组汇总</a>'
        if detail_label
        else ""
    )
    bridge_html = _home_company_rank_bridge_html(period, company_codes) if group_key == "company_profit_rank" else ""
    unit_html = '<div class="home-detail-unit-note">单位：万元</div>' if group_key == "expense_analysis" else ""
    title = f'{cfg["title"]} · {detail_label}' if detail_label else cfg["title"]
    detail_html = (
        '<div class="home-detail-overlay">'
        '<div class="home-detail-layer home-detail-modal">'
        '<div class="home-detail-header">'
        '<div>'
        f'{back_html}'
        f'<div class="home-detail-title">{_html(title)}</div>'
        '<div class="home-detail-subtitle">'
        f'{_html(_home_period_label(period))} · 范围：{_html(scope_label)} · {_html(cfg["subtitle"])}'
        '</div>'
        f'{bridge_html}'
        '</div>'
        f'<a class="home-detail-close" href="{_html(_app_query_href())}" target="_top" title="关闭详情层" aria-label="关闭详情层">×</a>'
        '</div>'
        f'<div class="home-detail-body">{unit_html}{table_html}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(detail_html, unsafe_allow_html=True)


@st.dialog("📈 指标下钻明细 (第二级)", width="large")
def show_metric_drilldown_dialog(
    metric_key: str,
    period: str,
    prev_period: str | None,
    scope_code: str | None,
    scope_label: str,
    business_group: str | None = None,
    company_codes: list[str] | None = None,
) -> None:
    cfg = HOME_DRILL_CONFIG.get(metric_key)
    if not cfg:
        st.warning("未找到可下钻的指标配置。")
        return

    st.markdown(f"##### {_home_period_label(period)} {cfg['title']}")
    st.caption(f"范围：{scope_label} | 数据源：事实表 + dim_company 组织架构聚合")

    resolved_company_codes = (
        company_codes
        if company_codes is not None
        else _resolve_scope_company_codes(scope_code, business_group=business_group)
    )
    drill_df = _load_metric_drilldown(metric_key, period, prev_period, resolved_company_codes)
    if len(drill_df) == 0:
        st.info("当前范围暂无可展示的下钻数据。")
        if st.button("关闭明细", use_container_width=True):
            st.rerun()
        return

    if px is None:
        st.warning("未检测到 plotly，无法展示树状图。请先执行: pip install plotly")
    else:
        chart_df = drill_df.copy()
        chart_df["集团根节点"] = cfg["root"]
        fig = px.treemap(
            chart_df,
            path=["集团根节点", "业务板块"],
            values="绝对值",
            color="占比(%)",
            color_continuous_scale="Blues",
        )
        fig.update_traces(
            textinfo="label+text",
            textposition="middle center",
            customdata=chart_df[[cfg["current_col"], "占比(%)"]],
            texttemplate=(
                "<b>%{label}</b><br>"
                "<span style='color:#d92d20; font-size:24px'><b>%{customdata[0]:,.0f}</b></span><br>"
                "占比: %{customdata[1]:.2f}%"
            ),
            textfont=dict(size=18),
        )
        fig.update_layout(
            margin=dict(t=10, l=10, r=10, b=10),
            uniformtext=dict(minsize=14, mode="hide"),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### 构成明细表")
    display_cols = ["业务板块", cfg["current_col"], cfg["previous_col"], "占比(%)"]
    st.dataframe(
        drill_df[display_cols].style.format(
            {
                cfg["current_col"]: "{:,.2f}",
                cfg["previous_col"]: "{:,.2f}",
                "占比(%)": "{:.2f}%",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    if st.button("关闭明细", use_container_width=True):
        st.rerun()


def render_home():
    periods = get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间")
        return

    summary_mode_options = ["默认公司"]
    group_options = _get_business_group_options()

    st.markdown('<div class="page-header">经营分析驾驶舱</div>', unsafe_allow_html=True)
    filters = _render_workspace_filter_bar(
        key_prefix="home",
        periods=periods,
        summary_mode_options=summary_mode_options,
        group_options=group_options,
        period_label="统计周期",
        note="可先按年份、月份和所属板块快速筛选，再结合期间进行精确定位。",
    )

    period = filters["period"]
    selected_group = filters["business_group"]
    scope_code = None
    prev_period = _previous_period(periods, period)
    filtered_company_codes = _resolve_filter_company_codes(filters, scope_code)

    try:
        dashboard = _get_cached_home_dashboard(period, scope_code, tuple(filtered_company_codes))
        dashboard = _apply_home_budget_kpi_overrides(dashboard, period)
    except Exception as exc:
        st.error(f"首页指标计算失败: {exc}")
        return

    income = dashboard.get("income", {})
    budget = dashboard.get("budget", {})
    completeness = dashboard.get("import_completeness", {})
    anomalies = dashboard.get("anomalies", [])
    scope_label = _workspace_scope_label(filters)

    hero_stats = [
        ("导入完整度", _fmt_percent(completeness.get("score"))),
        ("异常事项", f"{len(anomalies)} 条"),
        ("覆盖公司", f"{dashboard.get('scope_company_count', 0)} 家"),
    ]
    hero_stat_html = "".join(
        f'<div class="bi-hero-stat"><div class="num">{_html(value)}</div><div class="txt">{_html(label)}</div></div>'
        for label, value in hero_stats
    )
    _render_html(
        f"""
        <div class="bi-hero">
            <div>
                <div class="bi-eyebrow">BI 经营分析大屏</div>
                <div class="bi-title">利润、预算、现金流一屏看清</div>
                <div class="bi-subtitle">{_html(period)} · {_html(scope_label)} · 从经营结果、预算偏差、资金安全和异常事项四条线同步判断。</div>
            </div>
            <div class="bi-hero-side">{hero_stat_html}</div>
        </div>
        """
    )

    kpis = dashboard.get("kpis", [])
    drill_label_map = {
        cfg["label"]: metric_key
        for metric_key, cfg in HOME_DRILL_CONFIG.items()
    }
    drill_metric = _get_query_param("drill_metric")
    _render_bi_kpi_grid(
        kpis,
        drill_label_map=drill_label_map,
        selected_metric_key=drill_metric,
        extra_grid_class="home-top-kpi-grid",
    )
    st.caption("提示：点击 KPI 数值可在当前页下钻到下一层级，查看构成明细。")

    if drill_metric in HOME_DRILL_CONFIG:
        _render_metric_drilldown_layer(
            drill_metric,
            period,
            prev_period,
            scope_label,
            filtered_company_codes,
        )
    home_group = _get_query_param("home_group")
    selected_home_group = home_group if drill_metric not in HOME_DRILL_CONFIG and home_group in HOME_CARD_GROUP_CONFIG else None
    if selected_home_group:
        _render_home_card_group_layer(
            selected_home_group,
            period,
            scope_label,
            filtered_company_codes,
        )
    expense_analysis = _home_expense_analysis_for_scope(period, tuple(filtered_company_codes))
    funds_summary = _home_funds_summary_for_scope(period, tuple(filtered_company_codes))
    company_rank_summary = _home_company_rank_summary_for_scope(period, tuple(filtered_company_codes))
    operating_anomaly_counts = _home_operating_anomaly_summary_counts_for_scope(period, tuple(filtered_company_codes))

    _render_html(
        f"""
        <div class="bi-section-grid home-card-group-grid">
            {_render_budget_execution_panel(_home_budget_summary_for_scope(period, filtered_company_codes), selected_home_group)}
            {_render_operating_summary_panel(_home_operating_summary_for_scope(period, tuple(filtered_company_codes)), selected_home_group)}
            {_render_expense_analysis_panel(expense_analysis, selected_home_group)}
            {_render_operating_anomaly_panel(operating_anomaly_counts, selected_home_group)}
            {_render_company_profit_rank_panel(company_rank_summary, selected_home_group)}
            {_render_funds_safety_panel(funds_summary, selected_home_group)}
            {_render_funds_turnover_risk_panel(funds_summary, selected_home_group)}
        </div>
        """
    )

def _period_range(periods: list[str], start_period: str, end_period: str) -> list[str]:
    ordered = sorted(str(p) for p in periods if p)
    if not ordered:
        return []
    if start_period not in ordered:
        start_period = ordered[0]
    if end_period not in ordered:
        end_period = ordered[-1]
    start_idx = ordered.index(start_period)
    end_idx = ordered.index(end_period)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    return ordered[start_idx:end_idx + 1]


def _sql_in(values: list[str], prefix: str, params: dict) -> str:
    holders = []
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        params[key] = value
        holders.append(f":{key}")
    return ", ".join(holders) if holders else "NULL"


def _empty_contribution_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["经营单元", "所属板块", "收入", "成本/费用", "经营利润", "利润率", "收入占比"]
    )


def _load_contribution_by_unit(periods: list[str], company_codes: list[str]) -> pd.DataFrame:
    if not periods or not company_codes:
        return _empty_contribution_frame()

    params: dict = {
        "income_item": INCOME_ITEM,
        "profit_item": NET_PROFIT_ITEM,
    }
    period_sql = _sql_in(periods, "contrib_period", params)
    company_sql = _company_filter_clause("i", company_codes, params, "contrib_company")
    cost_sql = _sql_in(COST_ITEMS, "contrib_cost", params)
    df = execute_sql(
        f"""
        SELECT
            i.company_code AS 公司编码,
            COALESCE(c.name, i.company_code) AS 经营单元,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS 所属板块,
            SUM(CASE WHEN i.item_name = :income_item THEN i.period1_value ELSE 0 END) AS 收入,
            SUM(CASE WHEN i.item_name IN ({cost_sql}) THEN i.period1_value ELSE 0 END) AS 成本费用,
            SUM(CASE WHEN i.item_name = :profit_item THEN i.period1_value ELSE 0 END) AS 经营利润
        FROM income_statement i
        LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(i.company_code AS TEXT)
        LEFT JOIN dim_company d ON CAST(d.company_id AS TEXT) = CAST(i.company_code AS TEXT)
        WHERE i.period IN ({period_sql}) {company_sql}
        GROUP BY i.company_code, COALESCE(c.name, i.company_code), COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组')
        """,
        params,
    )
    if len(df) == 0:
        return _empty_contribution_frame()
    df["收入"] = pd.to_numeric(df["收入"], errors="coerce").fillna(0.0)
    df["成本/费用"] = pd.to_numeric(df["成本费用"], errors="coerce").fillna(0.0).abs()
    df["经营利润"] = pd.to_numeric(df["经营利润"], errors="coerce").fillna(0.0)
    df["利润率"] = df.apply(lambda row: _safe_ratio_ui(row["经营利润"], row["收入"]), axis=1)
    total_income = _safe_float(df["收入"].sum())
    df["收入占比"] = df["收入"].apply(lambda value: _safe_ratio_ui(value, total_income))
    return df[["经营单元", "所属板块", "收入", "成本/费用", "经营利润", "利润率", "收入占比"]].sort_values(
        "收入", ascending=False
    )


def _load_contribution_by_month(periods: list[str], company_codes: list[str]) -> pd.DataFrame:
    if not periods or not company_codes:
        return pd.DataFrame(columns=["期间", "收入", "成本/费用", "经营利润", "利润率"])

    params: dict = {
        "income_item": INCOME_ITEM,
        "profit_item": NET_PROFIT_ITEM,
    }
    period_sql = _sql_in(periods, "contrib_month_period", params)
    company_sql = _company_filter_clause("i", company_codes, params, "contrib_month_company")
    cost_sql = _sql_in(COST_ITEMS, "contrib_month_cost", params)
    df = execute_sql(
        f"""
        SELECT
            i.period AS 期间,
            SUM(CASE WHEN i.item_name = :income_item THEN i.period1_value ELSE 0 END) AS 收入,
            SUM(CASE WHEN i.item_name IN ({cost_sql}) THEN i.period1_value ELSE 0 END) AS 成本费用,
            SUM(CASE WHEN i.item_name = :profit_item THEN i.period1_value ELSE 0 END) AS 经营利润
        FROM income_statement i
        WHERE i.period IN ({period_sql}) {company_sql}
        GROUP BY i.period
        ORDER BY i.period
        """,
        params,
    )
    if len(df) == 0:
        return pd.DataFrame(columns=["期间", "收入", "成本/费用", "经营利润", "利润率"])
    df["收入"] = pd.to_numeric(df["收入"], errors="coerce").fillna(0.0)
    df["成本/费用"] = pd.to_numeric(df["成本费用"], errors="coerce").fillna(0.0).abs()
    df["经营利润"] = pd.to_numeric(df["经营利润"], errors="coerce").fillna(0.0)
    df["利润率"] = df.apply(lambda row: _safe_ratio_ui(row["经营利润"], row["收入"]), axis=1)
    return df[["期间", "收入", "成本/费用", "经营利润", "利润率"]]


def _load_budget_compare(periods: list[str], company_codes: list[str]) -> pd.DataFrame:
    if not periods:
        return pd.DataFrame(columns=["指标", "期间预算", "期间实际", "差异", "完成率"])
    year = str(periods[-1])[:4]
    month_count = len(periods)
    params: dict = {"year": year}
    company_filter = ""
    if company_codes:
        company_filter = f" AND (company_code IS NULL OR company_code IN ({_sql_in(company_codes, 'budget_company', params)}))"
    budget_df = execute_sql(
        f"""
        SELECT target_type, SUM(annual_target) AS annual_target
        FROM budget_targets
        WHERE budget_year = :year {company_filter}
        GROUP BY target_type
        """,
        params,
    )
    budget_map = {
        str(row["target_type"]): _safe_float(row["annual_target"])
        for _, row in budget_df.iterrows()
    } if len(budget_df) else {}

    month_df = _load_contribution_by_month(periods, company_codes)
    income_actual = _safe_float(month_df["收入"].sum()) if len(month_df) else 0.0
    profit_actual = _safe_float(month_df["经营利润"].sum()) if len(month_df) else 0.0
    rows = []
    for label, metric_key, actual in [
        ("收入", "income", income_actual),
        ("经营利润", "profit", profit_actual),
    ]:
        period_target = _safe_float(budget_map.get(metric_key)) * month_count / 12
        rows.append(
            {
                "指标": label,
                "期间预算": period_target,
                "期间实际": actual,
                "差异": actual - period_target,
                "完成率": _safe_ratio_ui(actual, period_target),
            }
        )
    return pd.DataFrame(rows)


def _render_finance_dataframe(df: pd.DataFrame, height: int = 420) -> None:
    if len(df) == 0:
        st.info("当前筛选范围暂无数据。")
        return
    config = {}
    for col in df.columns:
        if col in {"收入", "成本/费用", "经营利润", "期间预算", "期间实际", "差异"}:
            config[col] = st.column_config.NumberColumn(col, format="%,.2f")
        elif col in {"利润率", "收入占比", "完成率"}:
            config[col] = st.column_config.NumberColumn(col, format="%.2f%%")
    display = df.copy()
    for col in ["利润率", "收入占比", "完成率"]:
        if col in display.columns:
            display[col] = display[col].apply(lambda value: None if value is None else _safe_float(value) * 100)
    st.dataframe(display, use_container_width=True, hide_index=True, height=height, column_config=config)


def _safe_sheet_name(sheet_name: str, used_names: set[str]) -> str:
    safe_name = "".join(ch for ch in str(sheet_name) if ch not in r'[]:*?/\\')[:31] or "Sheet"
    base_name = safe_name
    suffix = 1
    while safe_name in used_names:
        suffix += 1
        safe_name = f"{base_name[:28]}_{suffix}"[:31]
    used_names.add(safe_name)
    return safe_name


def _excel_col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _is_blank_cell(value) -> bool:
    try:
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _xlsx_cell_xml(value, row_idx: int, col_idx: int) -> str:
    ref = f"{_excel_col_name(col_idx)}{row_idx}"
    if _is_blank_cell(value):
        return f'<c r="{ref}"/>'
    if isinstance(value, Number) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{float(value):.15g}</v></c>'
    text = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _minimal_xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    used_names: set[str] = set()
    normalized = [(_safe_sheet_name(name, used_names), df.copy()) for name, df in sheets.items()]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        sheet_overrides = "\n".join(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for idx, _ in enumerate(normalized, start=1)
        )
        archive.writestr(
            "[Content_Types].xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  {sheet_overrides}
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        sheets_xml = "\n".join(
            f'<sheet name="{xml_escape(sheet_name)}" sheetId="{idx}" r:id="rId{idx}"/>'
            for idx, (sheet_name, _) in enumerate(normalized, start=1)
        )
        archive.writestr(
            "xl/workbook.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets_xml}</sheets>
</workbook>""",
        )
        rels_xml = "\n".join(
            f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
            for idx, _ in enumerate(normalized, start=1)
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {rels_xml}
  <Relationship Id="rId{len(normalized) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Microsoft YaHei"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>""",
        )
        for sheet_idx, (_, df) in enumerate(normalized, start=1):
            rows = []
            headers = list(df.columns)
            rows.append(
                f'<row r="1">{"".join(_xlsx_cell_xml(col, 1, idx) for idx, col in enumerate(headers))}</row>'
            )
            for row_num, row in enumerate(df.itertuples(index=False, name=None), start=2):
                rows.append(
                    f'<row r="{row_num}">{"".join(_xlsx_cell_xml(value, row_num, idx) for idx, value in enumerate(row))}</row>'
                )
            end_col = _excel_col_name(max(len(headers) - 1, 0))
            end_row = max(len(df) + 1, 1)
            archive.writestr(
                f"xl/worksheets/sheet{sheet_idx}.xml",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{end_col}{end_row}"/>
  <sheetData>{''.join(rows)}</sheetData>
</worksheet>""",
            )
    return output.getvalue()


def _dataframes_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    engine = None
    try:
        import openpyxl  # noqa: F401
        engine = "openpyxl"
    except Exception:
        try:
            import xlsxwriter  # noqa: F401
            engine = "xlsxwriter"
        except Exception:
            return _minimal_xlsx_bytes(sheets)

    with pd.ExcelWriter(output, engine=engine) as writer:
        used_names: set[str] = set()
        for sheet_name, df in sheets.items():
            safe_name = _safe_sheet_name(sheet_name, used_names)
            df.to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            if engine == "openpyxl":
                for column_cells in worksheet.columns:
                    max_length = max(len(str(cell.value or "")) for cell in column_cells)
                    worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 10), 26)
    return output.getvalue()


def render_contribution_profit_statement():
    periods = get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间")
        return

    st.markdown('<div class="page-header">贡献式利润表</div>', unsafe_allow_html=True)
    filters = _render_workspace_filter_bar(
        key_prefix="contribution",
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="贡献式利润表筛选",
        period_mode="range",
        show_budget=True,
        note="第一版预算方案显示未设置预算；经营单元支持搜索多选，板块筛选会收窄经营单元列表。",
    )
    selected_periods = _period_range(periods, filters["start_period"], filters["end_period"])
    selected_group = filters["business_group"]
    company_codes = _resolve_filter_company_codes(filters)
    scope_label = _workspace_scope_label(filters)

    st.caption(
        f"范围：{scope_label} | 周期：{selected_periods[0]} 至 {selected_periods[-1]} | 数据源：损益表事实数据"
    )
    unit_df = _load_contribution_by_unit(selected_periods, company_codes)
    month_df = _load_contribution_by_month(selected_periods, company_codes)
    compare_df = _load_budget_compare(selected_periods, company_codes)

    revenue = _safe_float(month_df["收入"].sum()) if len(month_df) else 0.0
    cost = _safe_float(month_df["成本/费用"].sum()) if len(month_df) else 0.0
    profit = _safe_float(month_df["经营利润"].sum()) if len(month_df) else 0.0
    _render_bi_kpi_grid(
        [
            {"label": "期间收入", "value": revenue, "type": "money", "delta": None},
            {"label": "成本/费用", "value": cost, "type": "money", "delta": _safe_ratio_ui(cost, revenue)},
            {"label": "经营利润", "value": profit, "type": "money", "delta": _safe_ratio_ui(profit, revenue)},
            {"label": "覆盖月份", "value": len(selected_periods), "type": "number", "delta": None},
        ]
    )

    export_col, spacer_col = st.columns([1, 5])
    with export_col:
        st.download_button(
            "导出 Excel",
            _dataframes_to_excel_bytes(
                {
                    "单元利润表": unit_df,
                    "月度利润表": month_df,
                    "预实汇总表": compare_df,
                }
            ),
            file_name=f"贡献式利润表_{selected_periods[0]}_{selected_periods[-1]}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    tab_unit, tab_month, tab_budget = st.tabs(["贡献式利润表（单元）", "贡献式利润表（月度）", "预实汇总表"])
    with tab_unit:
        st.caption("按经营单元聚合，先看规模、成本费用和利润率。")
        _render_finance_dataframe(unit_df, height=460)
    with tab_month:
        st.caption("按月份横向观察收入、成本费用和利润变化。")
        _render_finance_dataframe(month_df, height=360)
    with tab_budget:
        st.caption("预算按年度目标折算到当前选择月份，后续可升级为月度预算曲线。")
        _render_finance_dataframe(compare_df, height=260)


def _default_break_even_rows() -> pd.DataFrame:
    rows = [
        {"分类": "收入", "预算项目": "课消收入", "产品/项目": "A产品", "计费周期": "人/年", "数量": 1.0, "金额": 4800.0, "预算比率(%)": 60.0},
        {"分类": "收入", "预算项目": "课消收入", "产品/项目": "B产品", "计费周期": "人/年", "数量": 1.0, "金额": 3900.0, "预算比率(%)": 40.0},
        {"分类": "可变成本", "预算项目": "教师课时费用", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 12.0},
        {"分类": "可变成本", "预算项目": "招生提成奖金", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 14.0},
        {"分类": "可变成本", "预算项目": "市场销售费用", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 7.0},
        {"分类": "可变成本", "预算项目": "教材物资费用", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 15.0},
        {"分类": "可变成本", "预算项目": "校区运营费用", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 7.0},
        {"分类": "可变成本", "预算项目": "品牌管理费用", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 11.0},
        {"分类": "可变成本", "预算项目": "税金", "产品/项目": "", "计费周期": "", "数量": 0.0, "金额": 0.0, "预算比率(%)": 4.0},
        {"分类": "固定成本", "预算项目": "租金物业", "产品/项目": "", "计费周期": "年", "数量": 1.0, "金额": 30000.0, "预算比率(%)": 0.0},
        {"分类": "固定成本", "预算项目": "教学人力基础薪酬+福利", "产品/项目": "", "计费周期": "人/年", "数量": 6.0, "金额": 50000.0, "预算比率(%)": 0.0},
        {"分类": "固定成本", "预算项目": "管理人力基础薪酬+福利", "产品/项目": "", "计费周期": "人/年", "数量": 1.0, "金额": 60000.0, "预算比率(%)": 0.0},
        {"分类": "固定成本", "预算项目": "折旧摊销", "产品/项目": "", "计费周期": "年", "数量": 5.0, "金额": 300000.0, "预算比率(%)": 0.0},
    ]
    return pd.DataFrame(rows)


def _calculate_break_even(rows: pd.DataFrame) -> dict:
    data = rows.copy()
    for col in ["数量", "金额", "预算比率(%)"]:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

    income_rows = data[data["分类"] == "收入"]
    variable_rows = data[data["分类"] == "可变成本"]
    fixed_rows = data[data["分类"] == "固定成本"]

    revenue = _safe_float((income_rows["数量"].clip(lower=0) * income_rows["金额"]).sum())
    variable_cost = _safe_float(variable_rows["金额"].sum())
    variable_cost += _safe_float((revenue * variable_rows["预算比率(%)"] / 100).sum())
    fixed_cost = _safe_float((fixed_rows["数量"].clip(lower=0) * fixed_rows["金额"]).sum())
    margin = revenue - variable_cost
    contribution_rate = _safe_ratio_ui(margin, revenue)
    profit = margin - fixed_cost
    profit_rate = _safe_ratio_ui(profit, revenue)
    avg_price = _safe_ratio_ui(
        (income_rows["数量"].clip(lower=0) * income_rows["金额"]).sum(),
        income_rows["数量"].clip(lower=0).sum(),
    )
    break_even_revenue = None
    if contribution_rate is not None and contribution_rate > 0:
        break_even_revenue = fixed_cost / contribution_rate
    break_even_people = None
    if break_even_revenue is not None and avg_price is not None and avg_price > 0:
        break_even_people = break_even_revenue / avg_price
    employee_count = _safe_float(
        fixed_rows[fixed_rows["预算项目"].astype(str).str.contains("人力", na=False)]["数量"].sum()
    )
    productivity = _safe_ratio_ui(revenue, employee_count)
    return {
        "营业收入": revenue,
        "可变成本": variable_cost,
        "边际利润": margin,
        "边际贡献率": contribution_rate,
        "固定成本": fixed_cost,
        "经营利润": profit,
        "利润率": profit_rate,
        "平均单价": avg_price,
        "盈亏平衡收入": break_even_revenue,
        "保本人数": break_even_people,
        "员工总人数": employee_count,
        "人均产能": productivity,
    }


def render_break_even_calculator():
    st.markdown('<div class="page-header">盈亏平衡测算</div>', unsafe_allow_html=True)
    if "break_even_rows" not in st.session_state:
        st.session_state.break_even_rows = _default_break_even_rows()
    if "break_even_plan_name" not in st.session_state:
        st.session_state.break_even_plan_name = "盈利测算"

    top_cols = st.columns([2.2, 1, 1, 1, 1.2])
    with top_cols[0]:
        st.text_input("测算方案", key="break_even_plan_name")
    with top_cols[1]:
        if st.button("新增测算", use_container_width=True):
            st.session_state.break_even_rows = _default_break_even_rows()
            st.session_state.break_even_plan_name = "新测算"
            st.rerun()
    with top_cols[2]:
        if st.button("重置", icon=":material/restart_alt:", use_container_width=True):
            st.session_state.break_even_rows = _default_break_even_rows()
            st.rerun()
    with top_cols[3]:
        st.button("保存", type="primary", use_container_width=True)
    with top_cols[4]:
        st.button("保存为预算", disabled=True, use_container_width=True)

    st.caption("第一版为页面原型：测算内容保存在当前会话中，后续再接数据库方案管理和预算草案。")
    edited = st.data_editor(
        st.session_state.break_even_rows,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        height=510,
        column_config={
            "分类": st.column_config.SelectboxColumn(
                "分类", options=["收入", "可变成本", "固定成本"], width="small"
            ),
            "预算项目": st.column_config.TextColumn("预算项目", width="medium"),
            "产品/项目": st.column_config.TextColumn("产品/项目", width="medium"),
            "计费周期": st.column_config.TextColumn("计费周期", width="small"),
            "数量": st.column_config.NumberColumn("数量", format="%.2f", width="small"),
            "金额": st.column_config.NumberColumn("金额", format="%,.2f", width="medium"),
            "预算比率(%)": st.column_config.NumberColumn("预算比率(%)", min_value=0.0, max_value=100.0, format="%.2f", width="small"),
        },
        key="break_even_editor",
    )
    st.session_state.break_even_rows = edited
    result = _calculate_break_even(edited)

    _render_bi_kpi_grid(
        [
            {"label": "盈亏平衡收入", "value": result["盈亏平衡收入"], "type": "money", "delta": None},
            {"label": "经营利润", "value": result["经营利润"], "type": "money", "delta": result["利润率"]},
            {"label": "边际贡献率", "value": result["边际贡献率"], "type": "percent", "delta": None},
            {"label": "保本人数", "value": result["保本人数"], "type": "number", "delta": None},
        ]
    )
    result_df = pd.DataFrame(
        [
            {"指标": "营业收入", "结果": result["营业收入"], "说明": "收入行数量 × 金额汇总"},
            {"指标": "可变成本", "结果": result["可变成本"], "说明": "直接金额 + 收入 × 预算比率"},
            {"指标": "固定成本", "结果": result["固定成本"], "说明": "固定成本行数量 × 金额汇总"},
            {"指标": "边际利润", "结果": result["边际利润"], "说明": "营业收入 - 可变成本"},
            {"指标": "盈亏平衡收入", "结果": result["盈亏平衡收入"], "说明": "固定成本 ÷ 边际贡献率"},
            {"指标": "平均单价", "结果": result["平均单价"], "说明": "收入金额 ÷ 收入数量"},
            {"指标": "员工总人数", "结果": result["员工总人数"], "说明": "固定成本中人力类数量合计"},
            {"指标": "人均产能", "结果": result["人均产能"], "说明": "营业收入 ÷ 员工总人数"},
        ]
    )
    st.markdown("##### 测算结果")
    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        column_config={"结果": st.column_config.NumberColumn("结果", format="%,.2f")},
    )


def _load_accounting_record_summary(periods: list[str], company_codes: list[str]) -> pd.DataFrame:
    if not periods or not company_codes:
        return pd.DataFrame(
            columns=["批次号", "公司编码", "经营单元", "所属板块", "期间", "报表类型", "状态", "总行数", "错误行数", "文件名", "导入时间"]
        )

    params: dict = {}
    period_sql = _sql_in(periods, "acct_period", params)
    company_sql = _sql_in(company_codes, "acct_company", params)
    df = execute_sql(
        f"""
        SELECT
            l.batch_no AS 批次号,
            l.company_code AS 公司编码,
            COALESCE(c.name, l.company_code) AS 经营单元,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS 所属板块,
            l.period AS 期间,
            l.report_type AS 报表类型,
            l.status AS 状态,
            l.total_rows AS 总行数,
            l.error_rows AS 错误行数,
            l.file_name AS 文件名,
            l.created_at AS 导入时间
        FROM import_logs l
        LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(l.company_code AS TEXT)
        LEFT JOIN dim_company d ON CAST(d.company_id AS TEXT) = CAST(l.company_code AS TEXT)
        WHERE l.period IN ({period_sql})
          AND l.company_code IN ({company_sql})
        ORDER BY l.created_at DESC, l.batch_no DESC
        """,
        params,
    )
    return df


def _accounting_source_options(summary_df: pd.DataFrame) -> list[str]:
    if len(summary_df) == 0:
        return []
    return [
        f"{row['批次号']} | {row['期间']} | {row['经营单元']} | {row['报表类型']}"
        for _, row in summary_df.iterrows()
    ]


def _batch_from_option(option: str) -> str:
    return option.split("|", 1)[0].strip() if option else ""


def _load_accounting_record_detail(batch_no: str, report_type: str | None = None) -> pd.DataFrame:
    if not batch_no:
        return pd.DataFrame()
    report_type = str(report_type or "")
    params = {"batch_no": batch_no}
    if report_type == "account_balance" or "科目余额" in report_type:
        return execute_sql(
            """
            SELECT
                ab.company_code AS 公司编码,
                COALESCE(c.name, ab.company_code) AS 经营单元,
                ab.period AS 期间,
                '科目余额表' AS 数据来源,
                ab.account_code AS 科目编码,
                ab.account_name AS 科目名称,
                ab.assist_dimensions AS 辅助核算,
                ab.opening_balance AS 期初余额,
                ab.debit_amount AS 借方发生额,
                ab.credit_amount AS 贷方发生额,
                ab.ending_balance AS 期末余额,
                ab.direction AS 方向,
                ab.created_at AS 入库时间
            FROM account_balance ab
            LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(ab.company_code AS TEXT)
            WHERE ab.import_batch = :batch_no
            ORDER BY ab.account_code, ab.id
            LIMIT 1000
            """,
            params,
        )
    if report_type == "income_statement" or "损益" in report_type:
        return execute_sql(
            """
            SELECT
                i.company_code AS 公司编码,
                COALESCE(c.name, i.company_code) AS 经营单元,
                i.period AS 期间,
                '损益表' AS 数据来源,
                i.item_name AS 业务科目,
                i.period1_value AS 本期金额,
                i.cumulative_value AS 本年累计,
                i.original_name AS 原始列名,
                i.created_at AS 入库时间
            FROM income_statement i
            LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(i.company_code AS TEXT)
            WHERE i.import_batch = :batch_no
            ORDER BY i.sort_order, i.id
            LIMIT 1000
            """,
            params,
        )
    if report_type == "balance_sheet" or "资产负债" in report_type:
        return execute_sql(
            """
            SELECT
                b.company_code AS 公司编码,
                COALESCE(c.name, b.company_code) AS 经营单元,
                b.period AS 期间,
                '资产负债表' AS 数据来源,
                b.side AS 报表方向,
                b.item_name AS 报表项目,
                b.line_number AS 行次,
                b.ending_balance AS 期末余额,
                b.opening_balance AS 年初余额,
                b.is_subtotal AS 是否小计,
                b.created_at AS 入库时间
            FROM balance_sheet b
            LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(b.company_code AS TEXT)
            WHERE b.import_batch = :batch_no
            ORDER BY b.side, b.sort_order, b.id
            LIMIT 1000
            """,
            params,
        )
    return pd.DataFrame()


def render_accounting_records():
    periods = get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间")
        return

    st.markdown('<div class="page-header">核算记录</div>', unsafe_allow_html=True)
    filters = _render_workspace_filter_bar(
        key_prefix="accounting",
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="记录筛选",
        period_mode="range",
        note="第一版按导入批次追溯，后续再扩展到分摊状态、业务科目和标准科目映射。",
    )
    selected_periods = _period_range(periods, filters["start_period"], filters["end_period"])
    company_codes = _resolve_filter_company_codes(filters)
    summary_df = _load_accounting_record_summary(selected_periods, company_codes)

    success_count = int((summary_df["状态"] == "成功").sum()) if len(summary_df) and "状态" in summary_df else 0
    error_rows = _safe_float(summary_df["错误行数"].sum()) if len(summary_df) and "错误行数" in summary_df else 0
    total_rows = _safe_float(summary_df["总行数"].sum()) if len(summary_df) and "总行数" in summary_df else 0
    _render_bi_kpi_grid(
        [
            {"label": "导入批次", "value": len(summary_df), "type": "number", "delta": None},
            {"label": "成功批次", "value": success_count, "type": "number", "delta": _safe_ratio_ui(success_count, len(summary_df))},
            {"label": "导入行数", "value": total_rows, "type": "number", "delta": None},
            {"label": "错误行数", "value": error_rows, "type": "number", "delta": _safe_ratio_ui(error_rows, total_rows)},
        ]
    )

    tab_summary, tab_detail = st.tabs(["核算记录汇总", "批次明细追溯"])
    with tab_summary:
        if len(summary_df) == 0:
            st.info("当前筛选范围暂无导入记录。")
        else:
            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True,
                height=460,
                column_config={
                    "总行数": st.column_config.NumberColumn("总行数", format="%d"),
                    "错误行数": st.column_config.NumberColumn("错误行数", format="%d"),
                },
            )
    with tab_detail:
        options = _accounting_source_options(summary_df)
        if not options:
            st.info("暂无可追溯批次。")
            return
        selected = st.selectbox("选择导入批次", options, key="accounting_batch_pick")
        batch_no = _batch_from_option(selected)
        row = summary_df[summary_df["批次号"] == batch_no].iloc[0].to_dict()
        st.caption(f"批次：{batch_no} | 数据源：{row.get('报表类型', '')} | 文件：{row.get('文件名', '')}")
        detail_df = _load_accounting_record_detail(batch_no, row.get("报表类型"))
        if len(detail_df) == 0:
            st.info("该批次暂无可展示的明细，可能是暂未接入的报表类型。")
        else:
            config = {}
            for col in detail_df.columns:
                if col in {"期初余额", "借方发生额", "贷方发生额", "期末余额", "本期金额", "本年累计", "年初余额"}:
                    config[col] = st.column_config.NumberColumn(col, format="%,.2f")
            st.dataframe(detail_df, use_container_width=True, hide_index=True, height=520, column_config=config)


def _render_fixed_template_sheet(
    sheet_name: str,
    key_prefix: str,
    min_col: int | None = None,
    max_col: int | None = None,
    table_skin: str | None = None,
) -> None:
    try:
        sheet = load_template_sheet(sheet_name, min_col=min_col, max_col=max_col)
        template_bytes = read_template_bytes()
    except TemplateWorkbookError as exc:
        st.error(str(exc))
        return

    st.download_button(
        "下载原始报表模板",
        template_bytes,
        file_name=sheet.source_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_download_template",
        use_container_width=True,
    )
    html = _picture_brief_template_skin_html(sheet.html) if table_skin == "picture_brief" else sheet.html
    st.markdown(html, unsafe_allow_html=True)


def _picture_brief_template_skin_html(sheet_html: str) -> str:
    return f"""
    <style>
      .picture-brief-template-skin .template-sheet-wrap {{
        overflow: auto;
        border: 1px solid #dbe5f2;
        background: #ffffff;
        max-height: 76vh;
        padding: 0;
        border-radius: 8px;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
      }}
      .picture-brief-template-skin .template-sheet {{
        border-collapse: collapse;
        border-spacing: 0;
        width: max-content;
        min-width: 100%;
        background: #ffffff;
        box-shadow: none;
      }}
      .picture-brief-template-skin .template-sheet td {{
        box-sizing: border-box;
        border: 1px solid #dbe5f2 !important;
        padding: 7px 10px !important;
        min-width: 64px;
        line-height: 1.32;
        white-space: pre-wrap;
        overflow: visible;
        vertical-align: middle !important;
        background-color: #ffffff !important;
        color: #10233f !important;
      }}
      .picture-brief-template-skin .template-sheet tbody tr:nth-child(even) td {{
        background-color: #fbfdff !important;
      }}
      .picture-brief-template-skin .template-sheet tbody tr:first-child td,
      .picture-brief-template-skin .template-sheet tr.template-header-row td,
      .picture-brief-template-skin .template-sheet tr.template-section-row td {{
        background: #eaf2ff !important;
        color: #10233f !important;
        font-weight: 800 !important;
        text-align: center !important;
        border-bottom: 1px solid #c9d8ec !important;
        height: 42px;
      }}
      .picture-brief-template-skin .template-sheet tr.template-section-row td {{
        background: #f2f7ff !important;
      }}
      .picture-brief-template-skin .template-sheet td.numeric-cell {{
        text-align: right !important;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }}
      .picture-brief-template-skin .template-sheet tr.template-risk-row td {{
        background-color: #fff1f1 !important;
      }}
      .picture-brief-template-skin .template-sheet td.negative-cell {{
        color: #d92d20 !important;
        background-color: #fff7f7 !important;
        font-weight: 750 !important;
      }}
      .picture-brief-template-skin .template-sheet tr.template-total-row td {{
        font-weight: 800 !important;
        background-color: #edf5ff !important;
        border-top: 2px solid #bad3f6 !important;
      }}
    </style>
    <div class="picture-brief-template-skin">{sheet_html}</div>
    """


PICTURE_BRIEF_SECTION_TITLES = ["素质中心报告", "其他模块报告", "对外投资情况", "各校区具体情况"]
PICTURE_BRIEF_OPERATING_ITEMS = ["收入合计", "净利润", "人工", "房租水电", "成本费用合计"]
PICTURE_BRIEF_OTHER_MODULE_SCOPES = [
    {"label": "学校", "root_code": "10108", "include_root": False, "fallback_codes": ["1010801"]},
    {"label": "幼儿园", "codes": ["1010702"]},
    {"label": "尔遇书城", "codes": ["1010601"]},
    {"label": "茶山托育", "codes": ["1010703"]},
    {"label": "青少年宫", "root_code": "10118", "include_root": False, "fallback_codes": ["1011801"]},
    {"label": "探幽文旅", "codes": ["10121"]},
]
PICTURE_BRIEF_INVESTMENT_SCOPES = [
    {"label": "深圳卓越", "codes": ["1010201"]},
    {"label": "中科心研", "codes": ["1020301"]},
    {"label": "武汉均衡", "codes": []},
    {"label": "多彩维度", "codes": []},
    {"label": "凤来置业", "codes": ["10119"]},
    {"label": "溢星空", "codes": []},
]
PICTURE_BRIEF_CAMPUS_SCOPES = [
    {"label": "莞小", "codes": ["101010120"]},
    {"label": "莞初", "codes": ["101010128"]},
    {"label": "莞高", "codes": ["101010121"]},
    {"label": "个性化", "codes": ["101010129"]},
    {"label": "南城", "codes": ["101010102"]},
    {"label": "石龙", "codes": ["101010103"]},
    {"label": "万江", "codes": ["101010104"]},
    {"label": "西平", "codes": ["101010106"]},
    {"label": "厚街", "codes": ["101010110"]},
    {"label": "石碣", "codes": ["101010111"]},
    {"label": "虎门", "codes": ["101010112"]},
    {"label": "石井", "codes": ["101010113"]},
    {"label": "西平三和", "codes": ["101010132"]},
    {"label": "高埗", "codes": ["101010135"]},
    {"label": "长安", "codes": ["101010134"]},
    {"label": "东泰", "codes": ["101010116"]},
    {"label": "虎翼营", "codes": ["101010123"]},
    {"label": "宏图", "codes": ["101010117"]},
    {"label": "茶山学前", "codes": ["101010131"]},
    {"label": "寮步石大", "codes": ["101010130"]},
    {"label": "南城虎翼", "codes": ["101010133"]},
    {"label": "拔创中心", "codes": ["101010136"]},
    {"label": "鸿福尔遇", "codes": ["1020401"]},
    {"label": "荣郡尔遇", "codes": ["1020402"]},
    {"label": "天骄尔遇", "codes": ["1020403"]},
    {"label": "金域尔遇", "codes": ["1020404"]},
    {"label": "星城尔遇", "codes": ["1020405"]},
    {"label": "龙景尔遇", "codes": ["1020406"]},
    {"label": "翡丽山尔遇", "codes": ["1020407"]},
    {"label": "西城楼尔遇", "codes": ["1020408"]},
]


def _picture_brief_columns(brief_type: str) -> tuple[int, int]:
    return (13, 20) if brief_type == "本年累计" else (2, 9)


def _picture_brief_text(value) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    return str(value).strip()


def _picture_brief_load_grid(brief_type: str) -> pd.DataFrame:
    min_col, max_col = _picture_brief_columns(brief_type)
    frame = load_template_sheet_frame("图片简报", formatted=True)
    columns = list(frame.columns)[min_col - 1:max_col]
    return frame.loc[:, columns].map(_picture_brief_text)


def _picture_brief_row_values(grid: pd.DataFrame, row_idx: int) -> list[str]:
    return [_picture_brief_text(value) for value in grid.iloc[row_idx].tolist()]


def _picture_brief_is_blank_row(values: list[str]) -> bool:
    return not any(_picture_brief_text(value) for value in values)


def _picture_brief_find_row(grid: pd.DataFrame, title: str) -> int | None:
    target = _picture_brief_text(title)
    for idx in range(len(grid)):
        if target in {_picture_brief_text(value) for value in grid.iloc[idx].tolist()}:
            return idx
    return None


def _picture_brief_is_numeric_text(value: str) -> bool:
    text = _picture_brief_text(value)
    if not text or not any(char.isdigit() for char in text):
        return False
    normalized = text.replace(",", "").replace("，", "").replace(" ", "")
    return bool(pd.notna(normalized)) and bool(re.fullmatch(r"[￥¥$€£()（）+\-–—\d.％%#DIV/0!]+", normalized))


def _picture_brief_is_negative_text(value: str) -> bool:
    text = _picture_brief_text(value).replace(",", "").replace("，", "").replace(" ", "")
    return text.startswith(("-", "−", "–", "—")) or (
        text.startswith(("(", "（")) and text.endswith((")", "）"))
    )


def _picture_brief_row_class(values: list[str]) -> str:
    joined = "".join(values)
    first = next((value for value in values if value), "")
    classes: list[str] = []
    if first in {"类别", "校区"}:
        classes.append("picture-brief-header-row")
    if first and (first in PICTURE_BRIEF_SECTION_TITLES or first == "集团经营情况"):
        classes.append("picture-brief-section-row")
    if any(token in joined for token in ("合计", "总计", "小计", "收入总额", "成本费用合计", "收入合计")):
        classes.append("picture-brief-total-row")
    if any(_picture_brief_is_negative_text(value) for value in values) and any(
        token in joined for token in ("净利润", "净利率", "亏损")
    ):
        classes.append("picture-brief-risk-row")
    return " ".join(classes)


def _picture_brief_metric_pairs(values: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    idx = 0
    while idx < len(values) - 1:
        label = _picture_brief_text(values[idx])
        value = ""
        value_idx = idx + 1
        for candidate_idx in range(idx + 1, min(idx + 4, len(values))):
            candidate = _picture_brief_text(values[candidate_idx])
            if not candidate:
                continue
            if _picture_brief_is_numeric_text(candidate) or any(char.isdigit() for char in candidate):
                value = candidate
                value_idx = candidate_idx
            break
        if label and value and not _picture_brief_is_numeric_text(label):
            pairs.append((label, value))
            idx = value_idx + 1
        else:
            idx += 1
    return pairs


def _picture_brief_kpi_labels(brief_type: str) -> list[str]:
    if brief_type == "本年累计":
        return ["本年累计收入", "经营净利润", "净利率", "素质中心完成任务情况", "已完成比例", "目标"]
    return ["本月经营收入", "经营净利润", "净利率", "人工", "租金", "成本费用合计"]


def _picture_brief_kpis(grid: pd.DataFrame, brief_type: str = "月报") -> list[tuple[str, str]]:
    start = _picture_brief_find_row(grid, "集团经营情况")
    if start is None:
        return []
    next_sections = [
        idx for title in PICTURE_BRIEF_SECTION_TITLES
        if (idx := _picture_brief_find_row(grid, title)) is not None and idx > start
    ]
    end = min(next_sections) if next_sections else min(start + 6, len(grid))
    pairs: list[tuple[str, str]] = []
    for row_idx in range(start + 1, end):
        values = _picture_brief_row_values(grid, row_idx)
        if _picture_brief_is_blank_row(values):
            continue
        pairs.extend(_picture_brief_metric_pairs(values))
    wanted = _picture_brief_kpi_labels(brief_type)
    by_label = {label: value for label, value in pairs}
    return [(label, by_label.get(label, "-")) for label in wanted]


def _picture_brief_db_signature() -> tuple[str, tuple[tuple[str, int, int, int], ...]]:
    path = get_db_path()
    signature: list[tuple[str, int, int, int]] = []
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            stat = candidate.stat()
            signature.append((str(candidate), 1, stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(candidate), 0, 0, 0))
    return str(path), tuple(signature)


def _picture_brief_pl_detail_rows(period: str) -> pd.DataFrame:
    db_path, db_signature = _picture_brief_db_signature()
    return _picture_brief_pl_detail_rows_cached(str(period), db_path, db_signature).copy(deep=True)


@st.cache_data(show_spinner=False)
def _picture_brief_pl_detail_rows_cached(
    period: str, db_path: str, db_signature: tuple[tuple[str, int, int, int], ...]
) -> pd.DataFrame:
    params = {"period": period}
    item_sql = _sql_in(PICTURE_BRIEF_OPERATING_ITEMS, "picture_item", params)
    try:
        return execute_sql(
            f"""
            SELECT
                id,
                company_code,
                item_code,
                item_name,
                amount,
                ytd_amount
            FROM pl_detail
            WHERE period = :period
              AND item_name IN ({item_sql})
            """,
            params,
        )
    except Exception:
        return pd.DataFrame(columns=["id", "company_code", "item_code", "item_name", "amount", "ytd_amount"])


def _picture_brief_preferred_pl_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if len(rows) == 0:
        return rows.copy()
    df = rows.copy()
    df["company_code"] = df.get("company_code", "").astype(str)
    df["item_name"] = df.get("item_name", "").astype(str)
    item_code = df.get("item_code", pd.Series([""] * len(df))).fillna("").astype(str)
    df["_priority"] = item_code.map(
        lambda value: 0 if value.startswith("OPERATING_") else (1 if value.startswith("SUMMARY_") else 2)
    )
    df["_row_id"] = pd.to_numeric(df.get("id", pd.Series(range(len(df)))), errors="coerce").fillna(0)
    df = df.sort_values(["company_code", "item_name", "_priority", "_row_id"], ascending=[True, True, False, True])
    return df.groupby(["company_code", "item_name"], as_index=False, group_keys=False).tail(1)


def _picture_brief_amount_text(value: float) -> str:
    try:
        amount_wan = float(value) / 10000
        amount = int(amount_wan + 0.5) if amount_wan >= 0 else int(amount_wan - 0.5)
        if amount == 0:
            amount = 0
        return f"{amount:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _picture_brief_target_text(value: float | None) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if not amount:
        return "-"
    if abs(amount) >= 100000000:
        return f"{amount / 100000000:.2f}".rstrip("0").rstrip(".") + "亿"
    return _picture_brief_amount_text(amount)


def _picture_brief_ratio_text(numerator: float, denominator: float) -> str:
    if not denominator:
        return "-"
    return f"{numerator / denominator * 100:.0f}%"


def _picture_brief_quality_income_target() -> float | None:
    path = Path(BUDGET_WORKBOOK_PATH)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _picture_brief_quality_income_target_cached(str(path), stat.st_mtime_ns, stat.st_size)


@st.cache_data(show_spinner=False)
def _picture_brief_quality_income_target_cached(path: str, mtime_ns: int, size: int) -> float | None:
    plan = read_budget_plan(path)
    if len(plan) == 0:
        return None
    matched = plan[
        (plan.get("module", "").astype(str) == "东莞素质中心")
        & (plan.get("unit_name", "").astype(str) == "东莞素质中心")
    ]
    if len(matched) == 0:
        matched = plan[plan.get("module", "").astype(str) == "东莞素质中心"]
    if len(matched) == 0:
        return None
    value = _safe_float(matched.iloc[0].get("income_budget"))
    return value if value else None


def _picture_brief_scope_values(rows: pd.DataFrame, company_codes: list[str] | None, use_ytd: bool) -> dict[str, float]:
    if len(rows) == 0:
        return {item: 0.0 for item in PICTURE_BRIEF_OPERATING_ITEMS}
    df = _picture_brief_preferred_pl_rows(rows)
    if company_codes is not None:
        code_set = {str(code) for code in company_codes}
        df = df[df["company_code"].astype(str).isin(code_set)]
    amount_col = "ytd_amount" if use_ytd else "amount"
    if amount_col not in df.columns:
        amount_col = "amount"
    df["_metric_amount"] = pd.to_numeric(df[amount_col], errors="coerce")
    if amount_col == "ytd_amount":
        fallback = pd.to_numeric(df.get("amount", 0), errors="coerce")
        df["_metric_amount"] = df["_metric_amount"].fillna(fallback)
    totals = df.groupby("item_name")["_metric_amount"].sum().to_dict()
    return {item: _safe_float(totals.get(item)) for item in PICTURE_BRIEF_OPERATING_ITEMS}


def _picture_brief_scope_has_pl_data(rows: pd.DataFrame, company_codes: list[str]) -> bool:
    if not company_codes or len(rows) == 0:
        return False
    df = _picture_brief_preferred_pl_rows(rows)
    code_set = {str(code) for code in company_codes}
    df = df[df["company_code"].astype(str).isin(code_set)]
    return bool(df["item_name"].astype(str).isin({"收入合计", "净利润"}).any())


def _picture_brief_resolve_scope_codes(scope: dict, company_tree: pd.DataFrame) -> list[str]:
    if "codes" in scope:
        return [str(code) for code in scope.get("codes", []) if str(code)]
    root_code = str(scope.get("root_code") or "")
    if not root_code:
        return []
    codes = _picture_brief_company_descendants_from_rows(
        company_tree, root_code, bool(scope.get("include_root", False))
    )
    return codes or [str(code) for code in scope.get("fallback_codes", []) if str(code)]


def _picture_brief_entity_metric_cells(rows: pd.DataFrame, company_codes: list[str], use_ytd: bool) -> list[str]:
    if not company_codes:
        return ["待确认", "待确认", "-"]
    if not _picture_brief_scope_has_pl_data(rows, company_codes):
        return ["待接入", "待接入", "-"]
    values = _picture_brief_scope_values(rows, company_codes, use_ytd)
    revenue = values.get("收入合计", 0.0)
    profit = values.get("净利润", 0.0)
    return [
        _picture_brief_amount_text(revenue),
        _picture_brief_amount_text(profit),
        _picture_brief_ratio_text(profit, revenue),
    ]


def _picture_brief_mapped_section_from_pl_rows(
    rows: pd.DataFrame,
    brief_type: str,
    scopes: list[dict],
    company_tree: pd.DataFrame,
    include_depreciation_row: bool = False,
) -> list[list[str]]:
    use_ytd = brief_type == "本年累计"
    labels = [str(scope.get("label") or "") for scope in scopes]
    metric_by_label = {
        label: _picture_brief_entity_metric_cells(
            rows, _picture_brief_resolve_scope_codes(scope, company_tree), use_ytd
        )
        for label, scope in zip(labels, scopes)
    }
    section = [
        ["类别", *labels],
        ["收入", *[metric_by_label[label][0] for label in labels]],
        ["净利润", *[metric_by_label[label][1] for label in labels]],
        ["净利率", *[metric_by_label[label][2] for label in labels]],
    ]
    if include_depreciation_row:
        section.append(["折摊前净利润", *["-" for _ in labels]])
    return section


def _picture_brief_campus_section_from_pl_rows(
    rows: pd.DataFrame, brief_type: str, company_tree: pd.DataFrame
) -> list[list[str]]:
    use_ytd = brief_type == "本年累计"
    split_at = ceil(len(PICTURE_BRIEF_CAMPUS_SCOPES) / 2)
    left_scopes = PICTURE_BRIEF_CAMPUS_SCOPES[:split_at]
    right_scopes = PICTURE_BRIEF_CAMPUS_SCOPES[split_at:]
    section = [["校区", "收入", "净利润", "净利率", "校区", "收入", "净利润", "净利率"]]
    for idx, left_scope in enumerate(left_scopes):
        left_label = str(left_scope.get("label") or "")
        left_values = _picture_brief_entity_metric_cells(
            rows, _picture_brief_resolve_scope_codes(left_scope, company_tree), use_ytd
        )
        if idx < len(right_scopes):
            right_scope = right_scopes[idx]
            right_label = str(right_scope.get("label") or "")
            right_values = _picture_brief_entity_metric_cells(
                rows, _picture_brief_resolve_scope_codes(right_scope, company_tree), use_ytd
            )
        else:
            right_label = ""
            right_values = ["", "", ""]
        section.append([left_label, *left_values, right_label, *right_values])
    return section


def _picture_brief_company_descendants(root_code: str, include_root: bool = False) -> list[str]:
    db_path, db_signature = _picture_brief_db_signature()
    companies = _picture_brief_company_tree_rows_cached(db_path, db_signature)
    return _picture_brief_company_descendants_from_rows(companies, root_code, include_root)


@st.cache_data(show_spinner=False)
def _picture_brief_company_tree_rows_cached(
    db_path: str, db_signature: tuple[tuple[str, int, int, int], ...]
) -> pd.DataFrame:
    try:
        return execute_sql("SELECT code, parent_code FROM companies")
    except Exception:
        return pd.DataFrame(columns=["code", "parent_code"])


def _picture_brief_company_descendants_from_rows(
    companies: pd.DataFrame, root_code: str, include_root: bool = False
) -> list[str]:
    if len(companies) == 0:
        return [root_code] if include_root else []
    children: dict[str, list[str]] = {}
    for _, row in companies.iterrows():
        code = str(row.get("code") or "")
        parent = str(row.get("parent_code") or "")
        if code:
            children.setdefault(parent, []).append(code)
    result: list[str] = [root_code] if include_root else []
    stack = list(children.get(str(root_code), []))
    seen = set(result)
    while stack:
        code = stack.pop(0)
        if code in seen:
            continue
        seen.add(code)
        result.append(code)
        stack.extend(children.get(code, []))
    return result


def _picture_brief_kpis_from_pl_rows(
    rows: pd.DataFrame, brief_type: str, company_tree: pd.DataFrame | None = None
) -> list[tuple[str, str]]:
    use_ytd = brief_type == "本年累计"
    values = _picture_brief_scope_values(rows, None, use_ytd)
    revenue = values.get("收入合计", 0.0)
    profit = values.get("净利润", 0.0)
    labels = _picture_brief_kpi_labels(brief_type)
    quality_revenue = 0.0
    quality_target = None
    if use_ytd:
        quality_codes = (
            _picture_brief_company_descendants_from_rows(company_tree, "10101", include_root=False)
            if company_tree is not None
            else _picture_brief_company_descendants("10101", include_root=False)
        )
        quality_values = _picture_brief_scope_values(rows, quality_codes, True)
        quality_revenue = quality_values.get("收入合计", 0.0)
        quality_target = _picture_brief_quality_income_target()
    value_by_label = {
        "本月经营收入": _picture_brief_amount_text(revenue),
        "本年累计收入": _picture_brief_amount_text(revenue),
        "经营净利润": _picture_brief_amount_text(profit),
        "净利率": _picture_brief_ratio_text(profit, revenue),
        "人工": _picture_brief_amount_text(values.get("人工", 0.0)),
        "租金": _picture_brief_amount_text(values.get("房租水电", 0.0)),
        "成本费用合计": _picture_brief_amount_text(values.get("成本费用合计", 0.0)),
        "素质中心完成任务情况": _picture_brief_amount_text(quality_revenue),
        "已完成比例": _picture_brief_ratio_text(quality_revenue, quality_target or 0.0),
        "目标": _picture_brief_target_text(quality_target),
    }
    return [(label, value_by_label.get(label, "-")) for label in labels]


def _picture_brief_kpis_from_pl_detail(period: str, brief_type: str) -> list[tuple[str, str]]:
    return _picture_brief_kpis_from_pl_rows(_picture_brief_pl_detail_rows(period), brief_type)


def _picture_brief_quality_section_from_pl_rows(
    rows: pd.DataFrame, brief_type: str, company_tree: pd.DataFrame | None = None
) -> list[list[str]]:
    use_ytd = brief_type == "本年累计"
    if company_tree is None:
        descendants = _picture_brief_company_descendants
    else:
        descendants = lambda code, include_root=False: _picture_brief_company_descendants_from_rows(
            company_tree, code, include_root
        )
    scopes = [
        ("素质中心", descendants("10101", include_root=False)),
        ("尔遇", descendants("10204", include_root=False)),
        ("尔遇管理中心", ["10204"]),
        ("管理中心", ["101"]),
    ]
    values_by_scope = [(label, _picture_brief_scope_values(rows, codes, use_ytd)) for label, codes in scopes]
    merged = {item: sum(values.get(item, 0.0) for _, values in values_by_scope) for item in PICTURE_BRIEF_OPERATING_ITEMS}

    def row_for(label: str, item: str) -> list[str]:
        values = [_picture_brief_amount_text(scope_values.get(item, 0.0)) for _, scope_values in values_by_scope]
        return [label, *values, _picture_brief_amount_text(merged.get(item, 0.0)), "", ""]

    revenue_values = [scope_values.get("收入合计", 0.0) for _, scope_values in values_by_scope]
    profit_values = [scope_values.get("净利润", 0.0) for _, scope_values in values_by_scope]
    margin_row = [
        "净利率",
        *[_picture_brief_ratio_text(profit, revenue) for profit, revenue in zip(profit_values, revenue_values)],
        _picture_brief_ratio_text(merged.get("净利润", 0.0), merged.get("收入合计", 0.0)),
        "",
        "",
    ]
    return [
        ["类别", "素质中心", "尔遇", "尔遇管理中心", "管理中心", "合并统计", "同比增长", "收入占比"],
        row_for("收入", "收入合计"),
        row_for("净利润", "净利润"),
        margin_row,
        row_for("人工", "人工"),
        row_for("租金", "房租水电"),
    ]


def _picture_brief_quality_section_from_pl_detail(period: str, brief_type: str) -> list[list[str]]:
    return _picture_brief_quality_section_from_pl_rows(_picture_brief_pl_detail_rows(period), brief_type)


def _picture_brief_operating_context(period: str) -> dict[str, list]:
    rows = _picture_brief_pl_detail_rows(period)
    db_path, db_signature = _picture_brief_db_signature()
    company_tree = _picture_brief_company_tree_rows_cached(db_path, db_signature)
    month_quality_rows = _picture_brief_quality_section_from_pl_rows(rows, "月报", company_tree)
    ytd_quality_rows = _picture_brief_quality_section_from_pl_rows(rows, "本年累计", company_tree)
    return {
        "month_kpis": _picture_brief_kpis_from_pl_rows(rows, "月报", company_tree),
        "ytd_kpis": _picture_brief_kpis_from_pl_rows(rows, "本年累计", company_tree),
        "month_quality_rows": month_quality_rows,
        "ytd_quality_rows": ytd_quality_rows,
        "month_other_rows": _picture_brief_mapped_section_from_pl_rows(
            rows, "月报", PICTURE_BRIEF_OTHER_MODULE_SCOPES, company_tree, include_depreciation_row=True
        ),
        "ytd_other_rows": _picture_brief_mapped_section_from_pl_rows(
            rows, "本年累计", PICTURE_BRIEF_OTHER_MODULE_SCOPES, company_tree, include_depreciation_row=True
        ),
        "month_investment_rows": _picture_brief_mapped_section_from_pl_rows(
            rows, "月报", PICTURE_BRIEF_INVESTMENT_SCOPES, company_tree
        ),
        "ytd_investment_rows": _picture_brief_mapped_section_from_pl_rows(
            rows, "本年累计", PICTURE_BRIEF_INVESTMENT_SCOPES, company_tree
        ),
        "month_campus_rows": _picture_brief_campus_section_from_pl_rows(rows, "月报", company_tree),
        "ytd_campus_rows": _picture_brief_campus_section_from_pl_rows(rows, "本年累计", company_tree),
    }


def _picture_brief_section_table(grid: pd.DataFrame, title: str) -> list[list[str]]:
    start = _picture_brief_find_row(grid, title)
    if start is None:
        return []
    following = [
        idx for other_title in PICTURE_BRIEF_SECTION_TITLES
        if other_title != title and (idx := _picture_brief_find_row(grid, other_title)) is not None and idx > start
    ]
    end = min(following) if following else len(grid)
    rows: list[list[str]] = []
    for row_idx in range(start + 1, end):
        values = _picture_brief_row_values(grid, row_idx)
        if _picture_brief_is_blank_row(values):
            continue
        rows.append(values)
    return _picture_brief_clean_section_rows(rows)


def _picture_brief_is_note_row(values: list[str]) -> bool:
    first = next((_picture_brief_text(value) for value in values if _picture_brief_text(value)), "")
    return first == "月份" or first.startswith("@") or first.startswith("第")


def _picture_brief_clean_section_rows(rows: list[list[str]]) -> list[list[str]]:
    data_rows = [row for row in rows if not _picture_brief_is_note_row(row)]
    if not data_rows:
        return []
    max_cols = max(len(row) for row in data_rows)
    normalized = [row + [""] * (max_cols - len(row)) for row in data_rows]
    keep_indices = [
        idx for idx in range(max_cols)
        if any(_picture_brief_text(row[idx]) for row in normalized)
    ]
    return [[row[idx] for idx in keep_indices] for row in normalized]


def _picture_brief_compact_display_columns(rows: list[list[str]]) -> list[list[str]]:
    normalized = _picture_brief_clean_section_rows(rows)
    if len(normalized) <= 1:
        return normalized
    max_cols = max(len(row) for row in normalized)
    padded = [row + [""] * (max_cols - len(row)) for row in normalized]
    keep_indices = [0]
    for idx in range(1, max_cols):
        if any(_picture_brief_text(row[idx]) for row in padded[1:]):
            keep_indices.append(idx)
    return [[row[idx] for idx in keep_indices] for row in padded]


def _picture_brief_section_lookup(rows: list[list[str]], row_label: str, col_label: str) -> str:
    if not rows:
        return "-"
    header = rows[0]
    col_idx = next((idx for idx, value in enumerate(header) if _picture_brief_text(value) == col_label), None)
    if col_idx is None:
        return "-"
    for row in rows[1:]:
        if row and _picture_brief_text(row[0]) == row_label and col_idx < len(row):
            return _picture_brief_text(row[col_idx]) or "-"
    return "-"


def _picture_brief_note_line(grid: pd.DataFrame, label: str, brief_type: str) -> str:
    kpis = dict(_picture_brief_kpis(grid, brief_type))
    quality_rows = _picture_brief_section_table(grid, "素质中心报告")
    other_rows = _picture_brief_section_table(grid, "其他模块报告")
    revenue = kpis.get("本月经营收入") or kpis.get("本年累计收入", "-")
    profit = kpis.get("经营净利润", "-")
    margin = kpis.get("净利率", "-")
    quality_revenue = _picture_brief_section_lookup(quality_rows, "收入", "合并统计")
    quality_profit = _picture_brief_section_lookup(quality_rows, "净利润", "合并统计")
    bookstore_revenue = _picture_brief_section_lookup(other_rows, "收入", "尔遇书城")
    bookstore_profit = _picture_brief_section_lookup(other_rows, "净利润", "尔遇书城")
    if all(value in {"", "-"} for value in [revenue, profit, margin, quality_revenue, quality_profit]):
        return ""
    return (
        f"{label}：集团收入 {revenue}，净利润 {profit}，净利率 {margin}；"
        f"素质中心合并收入 {quality_revenue}，净利润 {quality_profit}；"
        f"尔遇书城收入 {bookstore_revenue}，净利润 {bookstore_profit}。"
    )


def _picture_brief_auto_note_html(month_grid: pd.DataFrame, ytd_grid: pd.DataFrame) -> str:
    lines = [
        line for line in [
            _picture_brief_note_line(month_grid, "本月口径", "月报"),
            _picture_brief_note_line(ytd_grid, "本年累计口径", "本年累计"),
        ] if line
    ]
    if not lines:
        lines = ["暂无足够数据生成说明。"]
    items = "".join(f"<li>{_html(line)}</li>" for line in lines)
    return f"""
    <section class="picture-brief-note">
      <h3>经营简报说明</h3>
      <ul>{items}</ul>
    </section>
    """


def _picture_brief_generated_note_html(
    month_kpis: list[tuple[str, str]],
    ytd_kpis: list[tuple[str, str]],
    month_quality_rows: list[list[str]],
    ytd_quality_rows: list[list[str]],
) -> str:
    month = dict(month_kpis)
    ytd = dict(ytd_kpis)
    month_quality_revenue = _picture_brief_section_lookup(month_quality_rows, "收入", "合并统计")
    month_quality_profit = _picture_brief_section_lookup(month_quality_rows, "净利润", "合并统计")
    ytd_quality_revenue = _picture_brief_section_lookup(ytd_quality_rows, "收入", "合并统计")
    ytd_quality_profit = _picture_brief_section_lookup(ytd_quality_rows, "净利润", "合并统计")
    lines = [
        (
            f"本月口径：集团收入 {month.get('本月经营收入', '-')} 万，"
            f"净利润 {month.get('经营净利润', '-')} 万，净利率 {month.get('净利率', '-')}；"
            f"素质中心/尔遇/管理中心合并收入 {month_quality_revenue} 万，净利润 {month_quality_profit} 万。"
        ),
        (
            f"本年累计口径：集团收入 {ytd.get('本年累计收入', '-')} 万，"
            f"净利润 {ytd.get('经营净利润', '-')} 万，净利率 {ytd.get('净利率', '-')}；"
            f"素质中心/尔遇/管理中心合并收入 {ytd_quality_revenue} 万，净利润 {ytd_quality_profit} 万。"
        ),
    ]
    items = "".join(f"<li>{_html(line)}</li>" for line in lines)
    return f"""
    <section class="picture-brief-note">
      <h3>经营简报说明</h3>
      <ul>{items}</ul>
    </section>
    """


def _picture_brief_cell_html(value: str) -> str:
    classes: list[str] = []
    if _picture_brief_is_numeric_text(value):
        classes.append("picture-brief-num")
    if _picture_brief_is_negative_text(value):
        classes.append("picture-brief-negative")
    class_attr = f' class="{" ".join(classes)}"' if classes else ""
    return f"<td{class_attr}>{_html(value)}</td>"


def _picture_brief_table_html(title: str, rows: list[list[str]]) -> str:
    rows = _picture_brief_compact_display_columns(rows)
    if not rows:
        return f"""
        <section class="picture-brief-section">
          <h3>{_html(title)}</h3>
          <div class="picture-brief-empty">暂无数据</div>
        </section>
        """
    column_count = max(len(row) for row in rows)
    table_min_width = 170 + max(column_count - 1, 0) * 138
    colgroup = (
        "<colgroup>"
        '<col class="picture-brief-first-col">'
        + "".join('<col class="picture-brief-data-col">' for _ in range(max(column_count - 1, 0)))
        + "</colgroup>"
    )
    body = []
    for row_idx, raw_values in enumerate(rows):
        values = raw_values + [""] * (column_count - len(raw_values))
        row_classes = _picture_brief_row_class(values)
        if row_idx == 0 and "picture-brief-header-row" not in row_classes:
            row_classes = f"{row_classes} picture-brief-header-row".strip()
        class_attr = f' class="{row_classes}"' if row_classes else ""
        body.append(f"<tr{class_attr}>{''.join(_picture_brief_cell_html(value) for value in values)}</tr>")
    section_class = "picture-brief-section picture-brief-campus-section" if title == "各校区具体情况" else "picture-brief-section"
    table_classes = ["picture-brief-table"]
    if title == "各校区具体情况":
        table_classes.append("picture-brief-campus-table")
    if column_count > 4:
        table_classes.append("picture-brief-wide-table")
    table_class = " ".join(table_classes)
    return f"""
    <section class="{section_class}">
      <h3>{_html(title)}</h3>
      <div class="picture-brief-table-scroll">
        <table class="{table_class}" style="min-width:{table_min_width}px">
          {colgroup}
          <tbody>{''.join(body)}</tbody>
        </table>
      </div>
    </section>
    """


def _picture_brief_styles() -> str:
    return """
    <style>
      .picture-brief-filter {
        display: grid;
        grid-template-columns: minmax(120px, .8fr) minmax(120px, .8fr) minmax(190px, 1.1fr) auto;
        gap: 12px;
        align-items: end;
        margin: 8px 0 14px;
      }
      .picture-brief-page-title {
        font-size: 30px;
        line-height: 1.25;
      }
      [data-testid="stMain"] .block-container {
        max-width: min(100%, 1680px);
        padding-left: 2rem;
        padding-right: 2rem;
      }
      [data-testid="stMain"] label,
      [data-testid="stMain"] [data-testid="stRadio"] p,
      [data-testid="stMain"] [data-testid="stSelectbox"] p {
        font-size: 15px;
        font-weight: 750;
      }
      .picture-brief-kpi-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(140px, 1fr));
        gap: 10px;
        margin: 10px 0 18px;
        width: 100%;
      }
      .picture-brief-kpi {
        background: #ffffff;
        border: 1px solid #dbe5f2;
        border-radius: 8px;
        padding: 14px 15px;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
      }
      .picture-brief-kpi .label { color: #18314f; font-size: 15px; font-weight: 850; }
      .picture-brief-kpi .value {
        color: #1d4ed8;
        font-size: 30px;
        font-weight: 900;
        margin-top: 6px;
        letter-spacing: 0;
      }
      .picture-brief-kpi .picture-brief-kpi-primary { color: #1d4ed8; }
      .picture-brief-kpi .picture-brief-kpi-positive { color: #16a34a; }
      .picture-brief-kpi .picture-brief-kpi-negative { color: #dc2626; }
      .picture-brief-section { margin: 18px 0 22px; width: 100%; }
      .picture-brief-section h3 {
        margin: 0 0 8px;
        color: #10233f;
        font-size: 21px;
        font-weight: 850;
        padding-bottom: 8px;
        border-bottom: 1px solid #dbe5f2;
      }
      .picture-brief-table-scroll { overflow: auto; width: 100%; max-height: 70vh; }
      .picture-brief-table {
        width: 100%;
        min-width: 720px;
        table-layout: fixed;
        border-collapse: collapse;
        border-spacing: 0;
        background: #ffffff;
        color: #10233f;
        font-size: 16px;
      }
      .picture-brief-table col.picture-brief-first-col { width: 170px; }
      .picture-brief-table col.picture-brief-data-col { width: 138px; }
      .picture-brief-table td {
        border: 1px solid #dbe5f2;
        padding: 9px 11px;
        line-height: 1.42;
        vertical-align: middle;
        white-space: pre-wrap;
        overflow: visible;
        overflow-wrap: anywhere;
        word-break: break-word;
        text-align: center;
      }
      .picture-brief-table tr:nth-child(even) td { background: #fbfdff; }
      .picture-brief-table tr.picture-brief-header-row td,
      .picture-brief-table tr.picture-brief-section-row td {
        background: #eaf2ff;
        color: #10233f;
        font-weight: 850;
        text-align: center;
      }
      .picture-brief-table tr.picture-brief-header-row td {
        position: sticky;
        top: 0;
        z-index: 4;
      }
      .picture-brief-wide-table tr.picture-brief-header-row td:first-child {
        left: 0;
        z-index: 7;
        box-shadow: 2px 0 0 rgba(148, 163, 184, 0.24);
      }
      .picture-brief-wide-table td:first-child {
        position: sticky;
        left: 0;
        z-index: 3;
        background: #ffffff;
        box-shadow: 2px 0 0 rgba(148, 163, 184, 0.18);
      }
      .picture-brief-wide-table tr:nth-child(even) td:first-child { background: #fbfdff; }
      .picture-brief-wide-table tr.picture-brief-section-row td:first-child { background: #eaf2ff; }
      .picture-brief-wide-table tr.picture-brief-total-row td:first-child { background: #edf5ff; }
      .picture-brief-wide-table tr.picture-brief-risk-row td:first-child { background: #fff1f1; }
      .picture-brief-wide-table td.picture-brief-negative:first-child { background: #fff7f7; }
      .picture-brief-table tr.picture-brief-total-row td {
        background: #edf5ff;
        font-weight: 850;
        border-top: 2px solid #bad3f6;
      }
      .picture-brief-table tr.picture-brief-risk-row td { background: #fff1f1; }
      .picture-brief-table td.picture-brief-num {
        text-align: right;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }
      .picture-brief-table td.picture-brief-negative {
        color: #d92d20;
        background: #fff7f7;
        font-weight: 800;
      }
      .picture-brief-empty {
        color: #64748b;
        border: 1px dashed #cbd5e1;
        padding: 12px;
        background: #ffffff;
      }
      .picture-brief-campus-table td {
        max-width: none;
      }
      .picture-brief-campus-table {
        min-width: 920px;
      }
      .picture-brief-campus-table td:nth-child(1),
      .picture-brief-campus-table td:nth-child(5) {
        text-align: center;
        white-space: normal;
        word-break: break-word;
      }
      .picture-brief-note {
        margin-top: 18px;
        padding-top: 12px;
        border-top: 1px solid #dbe5f2;
        color: #10233f;
      }
      .picture-brief-note h3 {
        margin: 0 0 8px;
        font-size: 21px;
        font-weight: 850;
      }
      .picture-brief-note ul {
        margin: 0;
        padding-left: 20px;
      }
      .picture-brief-note li {
        margin: 4px 0;
        line-height: 1.62;
        font-size: 16px;
      }
      .picture-brief-trend {
        margin-top: 20px;
        padding-top: 12px;
        border-top: 1px solid #dbe5f2;
        width: 100%;
      }
      .picture-brief-trend h3 {
        font-size: 21px;
        font-weight: 850;
      }
      .picture-brief-trend-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
        width: 100%;
      }
      .picture-brief-trend-note {
        margin: 8px 0 0;
        color: #334155;
        font-size: 15px;
        line-height: 1.5;
      }
      @media (max-width: 1180px) {
        .picture-brief-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .picture-brief-filter { grid-template-columns: 1fr 1fr; }
        .picture-brief-trend-grid { grid-template-columns: 1fr; }
      }
    </style>
    """


def _picture_brief_kpi_value_class(label: str, value: str) -> str:
    if _picture_brief_is_negative_text(value):
        return "picture-brief-kpi-negative"
    if label in {"净利率", "已完成比例"} and value not in {"", "-"}:
        return "picture-brief-kpi-positive"
    return "picture-brief-kpi-primary"


def _picture_brief_kpi_html(kpis: list[tuple[str, str]]) -> str:
    cards = "".join(
        (
            f'<div class="picture-brief-kpi"><div class="label">{_html(label)}</div>'
            f'<div class="value {_picture_brief_kpi_value_class(label, value)}">{_html(value)}</div></div>'
        )
        for label, value in kpis
    )
    return f'<div class="picture-brief-kpi-grid">{cards}</div>'


def _picture_brief_trend_frame(selected_year: str, selected_month: str) -> pd.DataFrame:
    periods = [
        period for period in get_dashboard_periods()
        if str(period).startswith(str(selected_year)) and str(period)[4:6] <= str(selected_month).zfill(2)
    ]
    periods = sorted(set(str(period) for period in periods))
    if len(periods) < 2:
        return pd.DataFrame(columns=["期间", "收入", "累计收入", "净利润", "净利率"])

    params: dict = {"income_item": INCOME_ITEM, "profit_item": NET_PROFIT_ITEM}
    period_sql = _sql_in(periods, "picture_period", params)
    try:
        df = execute_sql(
            f"""
            SELECT
                period,
                SUM(CASE WHEN item_name = :income_item THEN period1_value ELSE 0 END) AS revenue,
                SUM(CASE WHEN item_name = :profit_item THEN period1_value ELSE 0 END) AS net_profit
            FROM income_statement
            WHERE period IN ({period_sql})
            GROUP BY period
            ORDER BY period
            """,
            params,
        )
    except Exception:
        df = pd.DataFrame()
    if len(df) == 0:
        return pd.DataFrame(columns=["期间", "收入", "累计收入", "净利润", "净利率"])

    rows: list[dict] = []
    for _, item in df.iterrows():
        period = str(item.get("period") or "")
        if not period:
            continue
        revenue = _safe_float(item.get("revenue"))
        net_profit = _safe_float(item.get("net_profit"))
        rows.append(
            {
                "期间": period,
                "收入": revenue,
                "净利润": net_profit,
                "净利率": net_profit / revenue if revenue else 0.0,
            }
        )
    trend_df = pd.DataFrame(rows).sort_values("期间")
    if len(trend_df) == 0:
        return pd.DataFrame(columns=["期间", "收入", "累计收入", "净利润", "净利率"])
    trend_df["累计收入"] = trend_df["收入"].cumsum()
    return trend_df


def _picture_brief_change_text(current: float, previous: float) -> str:
    if previous == 0:
        return "暂无可比变化"
    change = (current - previous) / abs(previous)
    direction = "上升" if change >= 0 else "下降"
    return f"{direction} {abs(change) * 100:.1f}%"


def _picture_brief_trend_conclusions(trend_df: pd.DataFrame) -> dict[str, str]:
    if len(trend_df) < 2:
        return {}
    ordered = trend_df.sort_values("期间").reset_index(drop=True)
    current = ordered.iloc[-1]
    previous = ordered.iloc[-2]
    period_month = str(current.get("期间", ""))[4:6].lstrip("0") or str(current.get("期间", ""))
    revenue_change = _picture_brief_change_text(_safe_float(current.get("收入")), _safe_float(previous.get("收入")))
    profit_change = _picture_brief_change_text(_safe_float(current.get("净利润")), _safe_float(previous.get("净利润")))
    margin_text = _fmt_percent(current.get("净利率"))
    return {
        "收入趋势": f"{period_month}月收入较上期{revenue_change}，累计收入为 {_fmt_money(current.get('累计收入'))}。",
        "净利润趋势": f"{period_month}月净利润较上期{profit_change}，净利率为 {margin_text}。",
    }


def _render_picture_brief_trends(selected_year: str, selected_month: str) -> None:
    st.markdown('<div class="picture-brief-trend"><h3>趋势图</h3></div>', unsafe_allow_html=True)
    trend_df = _picture_brief_trend_frame(selected_year, selected_month)
    if len(trend_df) == 0:
        st.info("暂无足够多期数据生成趋势")
        return
    if go is None:
        st.dataframe(trend_df, hide_index=True, use_container_width=True)
        return
    conclusions = _picture_brief_trend_conclusions(trend_df)
    columns = st.columns(2)
    st.markdown('<div class="picture-brief-trend-grid">', unsafe_allow_html=True)
    with columns[0]:
        revenue_fig = go.Figure()
        revenue_fig.add_bar(
            x=trend_df["期间"],
            y=trend_df["收入"],
            name="每月收入",
            marker_color="#3b82f6",
        )
        revenue_fig.add_scatter(
            x=trend_df["期间"],
            y=trend_df["累计收入"],
            name="累计收入",
            mode="lines+markers",
            line=dict(color="#1d4ed8", width=3),
            yaxis="y2",
        )
        revenue_fig.update_layout(
            title="收入趋势",
            height=340,
            margin=dict(l=8, r=8, t=42, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#ffffff",
            legend_title_text="",
            yaxis_title="每月收入",
            yaxis2=dict(title="累计收入", overlaying="y", side="right", showgrid=False),
            font=dict(size=14, color="#10233f"),
        )
        st.plotly_chart(revenue_fig, use_container_width=True)
        st.markdown(f'<div class="picture-brief-trend-note">{_html(conclusions.get("收入趋势", ""))}</div>', unsafe_allow_html=True)
    with columns[1]:
        profit_colors = ["#dc2626" if _safe_float(value) < 0 else "#16a34a" for value in trend_df["净利润"]]
        profit_fig = go.Figure()
        profit_fig.add_bar(
            x=trend_df["期间"],
            y=trend_df["净利润"],
            name="每月净利润",
            marker_color=profit_colors,
        )
        profit_fig.add_scatter(
            x=trend_df["期间"],
            y=trend_df["净利率"],
            name="净利率",
            mode="lines+markers",
            line=dict(color="#f59e0b", width=3),
            yaxis="y2",
        )
        profit_fig.update_layout(
            title="净利润趋势",
            height=340,
            margin=dict(l=8, r=8, t=42, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#ffffff",
            legend_title_text="",
            yaxis_title="每月净利润",
            yaxis2=dict(title="净利率", overlaying="y", side="right", tickformat=".0%", showgrid=False),
            font=dict(size=14, color="#10233f"),
        )
        st.plotly_chart(profit_fig, use_container_width=True)
        st.markdown(f'<div class="picture-brief-trend-note">{_html(conclusions.get("净利润趋势", ""))}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_multi_picture_brief():
    st.markdown('<div class="page-header picture-brief-page-title">图片简报</div>', unsafe_allow_html=True)
    st.markdown(_picture_brief_styles(), unsafe_allow_html=True)
    periods = get_dashboard_periods()
    latest_period = max(periods) if periods else "202603"
    years = sorted({period[:4] for period in periods}, reverse=True) or [latest_period[:4]]
    default_year_idx = years.index(latest_period[:4]) if latest_period[:4] in years else 0
    selected_year = years[default_year_idx]
    months = [period[4:6] for period in sorted(periods) if period.startswith(selected_year)] or [latest_period[4:6]]
    default_month = latest_period[4:6] if latest_period[:4] == selected_year and latest_period[4:6] in months else months[-1]
    col_year, col_month, col_type, col_query = st.columns([0.8, 0.8, 1.3, 0.8])
    with col_year:
        selected_year = st.selectbox("年份", years, index=default_year_idx, key="picture_brief_year")
    months = [period[4:6] for period in sorted(periods) if period.startswith(selected_year)] or [default_month]
    month_index = months.index(default_month) if default_month in months else len(months) - 1
    with col_month:
        selected_month = st.selectbox(
            "月份",
            months,
            index=month_index,
            format_func=lambda value: f"{int(value)}月" if str(value).isdigit() else str(value),
            key="picture_brief_month",
        )
    with col_type:
        brief_type = st.radio(
            "简报类型",
            ["月报", "本年累计"],
            horizontal=True,
            label_visibility="visible",
            key="multi_picture_brief_type",
        )
    with col_query:
        st.button("查询报表", type="primary", use_container_width=True, key="picture_brief_query")

    for _ in range(24):
        st.empty()

    try:
        grid = _picture_brief_load_grid(brief_type)
    except TemplateWorkbookError as exc:
        st.error(str(exc))
        return

    try:
        template_bytes = read_template_bytes()
        st.download_button(
            "下载原始报表模板",
            template_bytes,
            file_name="报表模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="multi_picture_template_download_template",
            use_container_width=True,
        )
    except TemplateWorkbookError:
        pass

    selected_period = f"{selected_year}{str(selected_month).zfill(2)}"
    operating_context = _picture_brief_operating_context(selected_period)
    month_kpis = operating_context["month_kpis"]
    ytd_kpis = operating_context["ytd_kpis"]
    current_kpis = ytd_kpis if brief_type == "本年累计" else month_kpis
    month_quality_rows = operating_context["month_quality_rows"]
    ytd_quality_rows = operating_context["ytd_quality_rows"]
    current_quality_rows = ytd_quality_rows if brief_type == "本年累计" else month_quality_rows
    section_rows = {
        "素质中心报告": current_quality_rows,
        "其他模块报告": operating_context["ytd_other_rows" if brief_type == "本年累计" else "month_other_rows"],
        "对外投资情况": operating_context["ytd_investment_rows" if brief_type == "本年累计" else "month_investment_rows"],
        "各校区具体情况": operating_context["ytd_campus_rows" if brief_type == "本年累计" else "month_campus_rows"],
    }

    _render_html(_picture_brief_kpi_html(current_kpis))
    for section_title in PICTURE_BRIEF_SECTION_TITLES:
        _render_html(_picture_brief_table_html(section_title, section_rows.get(section_title, [])))
    _render_html(_picture_brief_generated_note_html(month_kpis, ytd_kpis, month_quality_rows, ytd_quality_rows))


FUNDS_WARNING_VIEW_SCOPE_OPTIONS = ["全部单体公司", "只看校区", "只看管理中心", "只看书馆", "只看资金预警公司"]
FUNDS_WARNING_STATUS_OPTIONS = ["预警公司", "资金紧张", "资金关注", "资金安全", "数据待接入", "全部状态"]
FUNDS_WARNING_SORT_OPTIONS = ["按风险从高到低", "按资金周转系数从低到高", "按可使用周转资金从低到高", "按公司名称"]
FUNDS_WARNING_MONEY_COLUMNS = ["货币资金", "其他应收款", "其他应付款", "实收资本未达账", "可使用周转资金", "近6月平均经营成本"]
FUNDS_WARNING_GROUP_RATIO_EXCLUDED_CODES = {"1010201", "101020101"}
FUNDS_WARNING_BALANCE_ROOTS = ["1001", "1002", "1012", "1221", "2241"]
FUNDS_WARNING_BALANCE_ROOT_METRIC = {
    "cash_total": "cash",
    "1001": "cash",
    "1002": "cash",
    "1012": "cash",
    "1221_company": "other_receivable",
    "2241_company": "other_payable",
}
FUNDS_WARNING_BALANCE_NAME_ROOT = {
    "货币资金": "cash_total",
    "现金": "1001",
    "银行存款": "1002",
    "其他货币资金": "1012",
}


def _funds_warning_db_signature() -> tuple[str, tuple[tuple[str, int, int, int], ...]]:
    path = get_db_path()
    signature: list[tuple[str, int, int, int]] = []
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            stat = candidate.stat()
            signature.append((str(candidate), 1, stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            signature.append((str(candidate), 0, 0, 0))
    return str(path), tuple(signature)


def _funds_warning_period_options() -> list[str]:
    try:
        rows = execute_sql(
            """
            SELECT period FROM account_balance
            UNION
            SELECT period FROM pl_detail
            ORDER BY period
            """
        )
    except Exception:
        return get_dashboard_periods()
    periods = [str(item) for item in rows.get("period", pd.Series(dtype=str)).dropna().tolist()]
    return periods or get_dashboard_periods()


def _funds_warning_company_frame() -> pd.DataFrame:
    try:
        return execute_sql(
            """
            SELECT c.code,
                   c.name,
                   c.short_name,
                   c.tree_path,
                   COALESCE(d.business_group, '') AS business_group
            FROM companies c
            LEFT JOIN dim_company d ON d.company_id = c.code
            WHERE c.status = 1
              AND c.code <> 'ROOT'
            ORDER BY COALESCE(c.tree_path, c.code), c.code
            """
        )
    except Exception:
        return pd.DataFrame(columns=["code", "name", "short_name", "tree_path", "business_group"])


def _funds_warning_balance_metrics(period: str) -> pd.DataFrame:
    try:
        rows = execute_sql(
            """
            SELECT company_code, account_code, account_name, ending_balance
            FROM account_balance
            WHERE period = :period
            """,
            {"period": str(period)},
        )
    except Exception:
        return pd.DataFrame(columns=["company_code", "cash", "other_receivable", "other_payable", "has_balance_data"])
    return _funds_warning_preferred_balance_metrics(rows)


def _funds_warning_balance_root(account_code, account_name) -> str | None:
    code = str(account_code or "").strip()
    name = str(account_name or "").strip()
    if "其他应收款" in name and "公司往来" in name:
        return "1221_company"
    if "其他应付款" in name and "公司往来" in name:
        return "2241_company"
    for root in FUNDS_WARNING_BALANCE_ROOTS:
        if root in {"1221", "2241"}:
            continue
        if code == root or code.startswith(root):
            return root
    if name in FUNDS_WARNING_BALANCE_NAME_ROOT:
        return FUNDS_WARNING_BALANCE_NAME_ROOT[name]
    return None


def _funds_warning_is_parent_balance_row(account_code, account_name, root: str) -> bool:
    code = str(account_code or "").strip()
    name = str(account_name or "").strip()
    if root in {"1221_company", "2241_company"}:
        return False
    return root == "cash_total" or code == root or FUNDS_WARNING_BALANCE_NAME_ROOT.get(name) == root


def _funds_warning_preferred_balance_metrics(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ["company_code", "cash", "other_receivable", "other_payable", "has_balance_data"]
    if len(rows) == 0:
        return pd.DataFrame(columns=columns)
    df = rows.copy()
    company_codes = sorted({str(code) for code in df.get("company_code", pd.Series(dtype=str)).dropna().tolist()})
    df["_root"] = df.apply(lambda row: _funds_warning_balance_root(row.get("account_code"), row.get("account_name")), axis=1)
    df = df[df["_root"].notna()].copy()
    root_values: list[dict] = []
    if len(df) > 0:
        df["_amount"] = pd.to_numeric(df.get("ending_balance", 0), errors="coerce").fillna(0.0)
        df["_is_parent"] = df.apply(
            lambda row: _funds_warning_is_parent_balance_row(row.get("account_code"), row.get("account_name"), row["_root"]),
            axis=1,
        )
        for (company_code, root), group in df.groupby(["company_code", "_root"], dropna=False):
            parent_rows = group[group["_is_parent"]]
            effective = parent_rows if len(parent_rows) else group
            root_values.append(
                {
                    "company_code": str(company_code),
                    "root": str(root),
                    "metric": FUNDS_WARNING_BALANCE_ROOT_METRIC[str(root)],
                    "amount": float(effective["_amount"].sum()),
                }
            )

    root_df = pd.DataFrame(root_values, columns=["company_code", "root", "metric", "amount"])
    result_rows: list[dict] = []
    for company_code in company_codes:
        group = root_df[root_df["company_code"] == company_code]
        if (group["root"] == "cash_total").any():
            cash = float(group.loc[group["root"] == "cash_total", "amount"].sum())
        else:
            cash = float(group.loc[group["metric"] == "cash", "amount"].sum())
        result_rows.append(
            {
                "company_code": str(company_code),
                "cash": cash,
                "other_receivable": float(group.loc[group["metric"] == "other_receivable", "amount"].sum()),
                "other_payable": float(group.loc[group["metric"] == "other_payable", "amount"].sum()),
                "has_balance_data": True,
            }
        )
    return pd.DataFrame(result_rows, columns=columns)


def _funds_warning_recent_periods(period: str, limit: int = 6) -> list[str]:
    try:
        rows = execute_sql(
            """
            SELECT DISTINCT period
            FROM pl_detail
            WHERE period <= :period
            ORDER BY period DESC
            LIMIT :limit
            """,
            {"period": str(period), "limit": int(limit)},
        )
    except Exception:
        return [str(period)]
    periods = [str(item) for item in rows.get("period", pd.Series(dtype=str)).dropna().tolist()]
    return sorted(periods) or [str(period)]


def _funds_warning_preferred_cost_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if len(rows) == 0:
        return rows.copy()
    df = rows.copy()
    item_code = df.get("item_code", pd.Series([""] * len(df))).fillna("").astype(str)
    df["_priority"] = item_code.map(
        lambda value: 0 if value.startswith("OPERATING_") else (1 if value.startswith("SUMMARY_") else 2)
    )
    df["_row_id"] = pd.to_numeric(df.get("id", pd.Series(range(len(df)))), errors="coerce").fillna(0)
    df = df.sort_values(["period", "company_code", "_priority", "_row_id"], ascending=[True, True, False, True])
    return df.groupby(["period", "company_code"], as_index=False, group_keys=False).tail(1)


def _funds_warning_cost_metrics(period: str) -> pd.DataFrame:
    periods = _funds_warning_recent_periods(period)
    params = {f"period_{idx}": value for idx, value in enumerate(periods)}
    period_sql = ", ".join(f":period_{idx}" for idx in range(len(periods)))
    try:
        rows = execute_sql(
            f"""
            SELECT id, company_code, period, item_code, amount
            FROM pl_detail
            WHERE item_name = '成本费用合计'
              AND period IN ({period_sql})
            """,
            params,
        )
    except Exception:
        return pd.DataFrame(columns=["company_code", "avg_operating_cost", "cost_period_count"])
    df = _funds_warning_preferred_cost_rows(rows)
    if len(df) == 0:
        return pd.DataFrame(columns=["company_code", "avg_operating_cost", "cost_period_count"])
    df["_amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce")
    grouped = df.groupby("company_code", as_index=False).agg(
        avg_operating_cost=("_amount", "mean"),
        cost_period_count=("period", "nunique"),
    )
    return grouped


def _funds_warning_status(turnover_ratio) -> str:
    if turnover_ratio is None or pd.isna(turnover_ratio):
        return "成本数据待接入"
    ratio = float(turnover_ratio)
    if ratio < 2.0:
        return "资金紧张"
    if ratio < 3.0:
        return "资金关注"
    return "资金安全"


def _funds_warning_row_status(row) -> str:
    if not bool(row.get("has_balance_data", False)):
        return "资金数据待接入"
    if _safe_float(row.get("近6月平均经营成本", 0)) <= 0:
        return "成本数据待接入"
    return _funds_warning_status(row.get("资金周转系数"))


def _funds_warning_core_rows(
    companies: pd.DataFrame,
    balances: pd.DataFrame,
    costs: pd.DataFrame,
    *,
    include_detail_columns: bool,
) -> pd.DataFrame:
    detail_columns = [
        "company_code",
        "business_group",
        "公司/校区",
        "has_balance_data",
        "货币资金",
        "其他应收款",
        "其他应付款",
        "实收资本未达账",
        "可使用周转资金",
        "近6月平均经营成本",
        "资金周转系数",
        "资金状态",
        "cost_period_count",
    ]
    summary_columns = [
        "company_code",
        "business_group",
        "公司/校区",
        "has_balance_data",
        "货币资金",
        "其他应收款",
        "其他应付款",
        "可使用周转资金",
        "近6月平均经营成本",
        "资金周转系数",
        "资金状态",
    ]
    output_columns = detail_columns if include_detail_columns else summary_columns
    if len(companies) == 0:
        return pd.DataFrame(columns=output_columns)
    df = companies.copy()
    df["company_code"] = df["code"].astype(str)
    if "business_group" not in df.columns:
        df["business_group"] = ""
    df["business_group"] = df["business_group"].fillna("").astype(str)
    df["公司/校区"] = df.apply(
        lambda row: str(row.get("short_name") or row.get("name") or row.get("code") or ""),
        axis=1,
    )
    balances = balances.rename(
        columns={"cash": "货币资金", "other_receivable": "其他应收款", "other_payable": "其他应付款"}
    )
    balance_cols = ["company_code", "货币资金", "其他应收款", "其他应付款", "has_balance_data"]
    for col in balance_cols:
        if col not in balances.columns:
            balances[col] = True if col == "has_balance_data" else 0.0
    df = df.merge(balances[balance_cols], on="company_code", how="left")
    df = df.merge(costs[["company_code", "avg_operating_cost", "cost_period_count"]], on="company_code", how="left")
    df["has_balance_data"] = df["has_balance_data"].fillna(False).astype(bool)
    has_cost_data = df["avg_operating_cost"].notna() | df["cost_period_count"].notna()
    df = df[df["has_balance_data"] | has_cost_data].copy()
    if len(df) == 0:
        return pd.DataFrame(columns=output_columns)
    for col in ["货币资金", "其他应收款", "其他应付款", "avg_operating_cost"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["实收资本未达账"] = 0.0
    df["可使用周转资金"] = df["货币资金"] + df["其他应收款"] - df["其他应付款"] + df["实收资本未达账"]
    df["近6月平均经营成本"] = df["avg_operating_cost"]
    df["资金周转系数"] = df.apply(
        lambda row: row["可使用周转资金"] / row["近6月平均经营成本"]
        if row["has_balance_data"] and row["近6月平均经营成本"] > 0
        else None,
        axis=1,
    )
    missing_balance_mask = ~df["has_balance_data"]
    df.loc[missing_balance_mask, ["货币资金", "其他应收款", "其他应付款", "可使用周转资金"]] = pd.NA
    df["资金状态"] = df.apply(_funds_warning_row_status, axis=1)
    return df[output_columns]


def _funds_warning_build_rows(companies: pd.DataFrame, balances: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    return _funds_warning_core_rows(companies, balances, costs, include_detail_columns=True)


def _funds_warning_build_summary_rows(companies: pd.DataFrame, balances: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    return _funds_warning_core_rows(companies, balances, costs, include_detail_columns=False)


def _funds_warning_filter_scope_rows(rows: pd.DataFrame, view_scope: str) -> pd.DataFrame:
    if len(rows) == 0 or view_scope == "全部单体公司":
        return rows
    label = rows.get("公司/校区", pd.Series([""] * len(rows), index=rows.index)).fillna("").astype(str)
    group = rows.get("business_group", pd.Series([""] * len(rows), index=rows.index)).fillna("").astype(str)
    if view_scope == "只看校区":
        return rows[
            label.str.contains("校区", na=False)
            | group.str.contains("素质中心|学校|幼儿园|托育|青少年宫", regex=True, na=False)
        ]
    if view_scope == "只看管理中心":
        return rows[label.str.contains("管理中心", na=False) | group.str.contains("职能公司", na=False)]
    if view_scope == "只看书馆":
        return rows[label.str.contains("书馆|尔遇", regex=True, na=False) | group.str.contains("书馆", na=False)]
    if view_scope == "只看资金预警公司":
        return rows[rows["资金周转系数"].notna() & (rows["资金周转系数"] < 3.0)]
    return rows


def _funds_warning_filter_rows(rows: pd.DataFrame, status_filter: str) -> pd.DataFrame:
    if len(rows) == 0 or status_filter == "全部状态":
        return rows
    if status_filter == "预警公司":
        return rows[rows["资金周转系数"].notna() & (rows["资金周转系数"] < 3.0)]
    if status_filter == "数据待接入":
        return rows[rows["资金状态"].astype(str).str.contains("待接入", na=False)]
    return rows[rows["资金状态"] == status_filter]


def _funds_warning_sort_rows(rows: pd.DataFrame, sort_option: str) -> pd.DataFrame:
    if len(rows) == 0:
        return rows
    df = rows.copy()
    if sort_option == "按可使用周转资金从低到高":
        return df.sort_values(["可使用周转资金", "company_code"], na_position="last")
    if sort_option == "按公司名称":
        return df.sort_values(["公司/校区", "company_code"], na_position="last")
    if sort_option == "按资金周转系数从低到高":
        return df.sort_values(["资金周转系数", "company_code"], na_position="last")
    risk_order = {"资金紧张": 0, "资金关注": 1, "资金数据待接入": 2, "成本数据待接入": 2, "资金安全": 3}
    df["_risk_order"] = df["资金状态"].map(risk_order).fillna(4)
    return df.sort_values(["_risk_order", "资金周转系数", "可使用周转资金", "company_code"], na_position="last").drop(columns=["_risk_order"])


def _funds_warning_group_ratio_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if len(rows) == 0:
        return rows
    df = rows.copy()
    codes = df.get("company_code", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str)
    business_group = df.get("business_group", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str)
    return df[
        ~codes.isin(FUNDS_WARNING_GROUP_RATIO_EXCLUDED_CODES)
        & ~business_group.str.contains("对外投资", na=False)
        & df["has_balance_data"].fillna(False).astype(bool)
        & (pd.to_numeric(df["近6月平均经营成本"], errors="coerce") > 0)
    ]


def _funds_warning_group_turnover_ratio(rows: pd.DataFrame):
    scoped = _funds_warning_group_ratio_rows(rows)
    if len(scoped) == 0:
        return None
    total_cost = pd.to_numeric(scoped["近6月平均经营成本"], errors="coerce").fillna(0.0).sum()
    if total_cost <= 0:
        return None
    total_available = pd.to_numeric(scoped["可使用周转资金"], errors="coerce").fillna(0.0).sum()
    return float(total_available / total_cost)


def _funds_warning_kpis(rows: pd.DataFrame) -> dict[str, str]:
    if len(rows) == 0:
        return {
            "资金紧张公司数": "0",
            "资金关注公司数": "0",
            "集团资金周转系数": "-",
            "可使用周转资金合计": "0.0",
        }
    group_ratio = _funds_warning_group_turnover_ratio(rows)
    return {
        "资金紧张公司数": str(int((rows["资金状态"] == "资金紧张").sum())),
        "资金关注公司数": str(int((rows["资金状态"] == "资金关注").sum())),
        "集团资金周转系数": f"{group_ratio:.2f}" if group_ratio is not None else "-",
        "可使用周转资金合计": f"{rows['可使用周转资金'].sum() / 10000:,.1f}",
    }


def _funds_warning_money_text(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value) / 10000:,.1f}"
    except (TypeError, ValueError):
        return "-"


def _funds_warning_ratio_text(value) -> str:
    if value is None or pd.isna(value):
        return "待接入"
    return f"{float(value):.2f}"


def _funds_warning_status_tag(status: str) -> str:
    class_name = {
        "资金紧张": "funds-warning-status-tight",
        "资金关注": "funds-warning-status-watch",
        "资金安全": "funds-warning-status-safe",
    }.get(status, "funds-warning-status-pending")
    return f'<span class="funds-warning-status {class_name}">{_html(status)}</span>'


@st.cache_data(show_spinner=False, ttl=120)
def _home_company_business_group_lookup() -> dict[str, str]:
    try:
        rows = execute_sql(
            """
            SELECT c.code,
                   c.name,
                   c.short_name,
                   COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS business_group
            FROM companies c
            LEFT JOIN dim_company d ON d.company_id = c.code
            WHERE c.status = 1
            """
        )
    except Exception:
        return {}
    mapping: dict[str, str] = {}
    for item in rows.to_dict("records"):
        group = str(item.get("business_group") or "未分组")
        for key in (item.get("code"), item.get("name"), item.get("short_name")):
            text = str(key or "").strip()
            if text:
                mapping[text] = group
    return mapping


def _funds_warning_cell(value, numeric: bool = False) -> str:
    text = _html(value)
    negative_class = ""
    if numeric:
        raw = str(value).replace(",", "")
        negative_class = " funds-warning-negative" if raw.startswith("-") else ""
    return f'<td class="{"funds-warning-num" if numeric else "funds-warning-text"}{negative_class}">{text}</td>'


def _funds_warning_table_html(rows: pd.DataFrame) -> str:
    headers = [
        "公司/校区",
        "货币资金",
        "其他应收款",
        "其他应付款",
        "实收资本未达账",
        "可使用周转资金",
        "近6月平均经营成本",
        "资金周转系数",
        "资金状态",
    ]
    if len(rows) == 0:
        body = '<tr><td class="funds-warning-empty" colspan="9">暂无符合条件的公司</td></tr>'
    else:
        body_rows: list[str] = []
        for _, row in rows.iterrows():
            body_rows.append(
                "<tr>"
                + _funds_warning_cell(row["公司/校区"])
                + "".join(_funds_warning_cell(_funds_warning_money_text(row[col]), numeric=True) for col in FUNDS_WARNING_MONEY_COLUMNS)
                + _funds_warning_cell(_funds_warning_ratio_text(row["资金周转系数"]), numeric=True)
                + f'<td class="funds-warning-text">{_funds_warning_status_tag(str(row["资金状态"]))}</td>'
                + "</tr>"
            )
        body = "".join(body_rows)
    header_html = "".join(f"<th>{_html(header)}</th>" for header in headers)
    return f"""
    <div class="funds-warning-table-head">
      <h3>公司资金周转预警清单</h3>
      <span>单位：万元</span>
    </div>
    <div class="funds-warning-table-wrap">
      <table class="funds-warning-table">
        <colgroup>
          <col class="funds-warning-company-col">
          <col span="8" class="funds-warning-data-col">
        </colgroup>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """


def _funds_warning_styles() -> str:
    return """
    <style>
      .funds-warning-kpis { display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:14px; margin:12px 0 18px; }
      .funds-warning-card { background:#fff; border:1px solid #dbe5f2; border-radius:10px; padding:16px 18px; box-shadow:0 8px 22px rgba(15,23,42,.04); }
      .funds-warning-card-label { color:#475569; font-weight:700; font-size:14px; margin-bottom:8px; }
      .funds-warning-card-value { color:#1d4ed8; font-size:28px; line-height:1.15; font-weight:850; font-variant-numeric:tabular-nums; }
      [class*="st-key-funds_warning_query"] { padding-top: 1.72rem; }
      [class*="st-key-funds_warning_query"] button { min-height: 42px !important; }
      .funds-warning-filter-note { margin:-2px 0 12px; color:#64748b; font-size:13px; font-weight:650; }
      .funds-warning-table-head { display:flex; align-items:center; justify-content:space-between; margin:18px 0 8px; }
      .funds-warning-table-head h3 { margin:0; color:#10233f; font-size:20px; font-weight:850; }
      .funds-warning-table-head span { color:#64748b; font-size:13px; font-weight:700; }
      .funds-warning-table-wrap { width:100%; overflow:auto; max-height:68vh; border:1px solid #dbe5f2; border-radius:8px; background:#fff; }
      .funds-warning-table { width:100%; min-width:1180px; border-collapse:collapse; table-layout:fixed; color:#10233f; font-size:15px; }
      .funds-warning-company-col { width:220px; }
      .funds-warning-data-col { width:120px; }
      .funds-warning-table th { position:sticky; top:0; z-index:4; background:#eaf2ff; border:1px solid #d7e4f5; padding:11px 10px; text-align:center; font-weight:850; }
      .funds-warning-table th:first-child { left:0; z-index:7; box-shadow:2px 0 0 rgba(148,163,184,.24); }
      .funds-warning-table td { border:1px solid #dbe5f2; padding:10px 10px; vertical-align:middle; background:#fff; }
      .funds-warning-table tbody tr:nth-child(even) td { background:#fbfdff; }
      .funds-warning-table td:first-child { position:sticky; left:0; z-index:3; background:#fff; box-shadow:2px 0 0 rgba(148,163,184,.18); }
      .funds-warning-table tbody tr:nth-child(even) td:first-child { background:#fbfdff; }
      .funds-warning-text { text-align:center; overflow-wrap:anywhere; }
      .funds-warning-num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
      .funds-warning-negative { color:#dc2626; font-weight:750; }
      .funds-warning-status { display:inline-flex; align-items:center; justify-content:center; min-width:68px; padding:4px 9px; border-radius:999px; font-size:13px; font-weight:800; }
      .funds-warning-status-tight { color:#b91c1c; background:#fee2e2; }
      .funds-warning-status-watch { color:#b45309; background:#fef3c7; }
      .funds-warning-status-safe { color:#047857; background:#dcfce7; }
      .funds-warning-status-pending { color:#475569; background:#e2e8f0; }
      .funds-warning-empty { text-align:center; color:#64748b; padding:20px; }
      .funds-warning-note { margin-top:14px; color:#475569; font-size:13px; line-height:1.7; }
      @media (max-width: 900px) { .funds-warning-kpis { grid-template-columns:repeat(2,minmax(150px,1fr)); } }
    </style>
    """


def render_funds_warning():
    st.markdown('<div class="page-header">资金预警</div>', unsafe_allow_html=True)
    st.markdown(_funds_warning_styles(), unsafe_allow_html=True)
    periods = _funds_warning_period_options()
    latest_period = max(periods) if periods else "202603"
    years = sorted({period[:4] for period in periods}, reverse=True) or [latest_period[:4]]
    selected_year = st.session_state.get("funds_warning_year", latest_period[:4])
    if selected_year not in years:
        selected_year = latest_period[:4]
    months = [period[4:6] for period in sorted(periods) if period.startswith(selected_year)] or [latest_period[4:6]]
    default_month = latest_period[4:6] if latest_period.startswith(selected_year) and latest_period[4:6] in months else months[-1]

    companies = _funds_warning_company_frame()
    col_year, col_month, col_scope, col_status, col_sort, col_query = st.columns([0.75, 0.75, 1.25, 1.05, 1.45, 0.9])
    with col_year:
        selected_year = st.selectbox("年份", years, index=years.index(selected_year), key="funds_warning_year")
    months = [period[4:6] for period in sorted(periods) if period.startswith(selected_year)] or [default_month]
    selected_month = st.session_state.get("funds_warning_month", default_month)
    if selected_month not in months:
        selected_month = default_month
    with col_month:
        selected_month = st.selectbox(
            "月份",
            months,
            index=months.index(selected_month),
            format_func=lambda value: f"{int(value)}月" if str(value).isdigit() else str(value),
            key="funds_warning_month",
        )
    with col_scope:
        selected_scope = st.selectbox(
            "查看范围",
            FUNDS_WARNING_VIEW_SCOPE_OPTIONS,
            index=0,
            key="funds_warning_scope",
        )
    with col_status:
        selected_status = st.selectbox(
            "资金状态",
            FUNDS_WARNING_STATUS_OPTIONS,
            index=0,
            key="funds_warning_status",
        )
    with col_sort:
        selected_sort = st.selectbox(
            "排序方式",
            FUNDS_WARNING_SORT_OPTIONS,
            index=0,
            key="funds_warning_sort",
        )
    with col_query:
        st.button("查询预警", type="primary", use_container_width=True, key="funds_warning_query")
    st.markdown(
        '<div class="funds-warning-filter-note">默认展示资金周转系数低于 3.0 的单体公司；资金类数据仅取科目余额表。</div>',
        unsafe_allow_html=True,
    )

    selected_period = f"{selected_year}{str(selected_month).zfill(2)}"
    balances = _funds_warning_balance_metrics(selected_period)
    costs = _funds_warning_cost_metrics(selected_period)
    rows = _funds_warning_build_rows(companies, balances, costs)
    scoped_rows = _funds_warning_filter_scope_rows(rows, selected_scope)
    filtered_rows = _funds_warning_sort_rows(_funds_warning_filter_rows(scoped_rows, selected_status), selected_sort)
    kpis = _funds_warning_kpis(rows)
    card_html = "".join(
        f'<div class="funds-warning-card"><div class="funds-warning-card-label">{_html(label)}</div><div class="funds-warning-card-value">{_html(value)}</div></div>'
        for label, value in kpis.items()
    )
    _render_html(f'<div class="funds-warning-kpis">{card_html}</div>')
    _render_html(_funds_warning_table_html(filtered_rows))
    st.markdown(
        """
        <div class="funds-warning-note">
        口径说明：可使用周转资金 = 货币资金 + 其他应收款 - 其他应付款 + 实收资本未达账。
        资金周转系数 = 可使用周转资金 / 近6月平均经营成本。
        资金周转系数 &lt; 2.0 为资金紧张，2.0-3.0 为资金关注，&gt;= 3.0 为资金安全。
        投资计划未接入前，实收资本未达账按 0 处理；成本期间不足 6 个月时按已有期间平均。
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_multi_income_statement():
    st.markdown('<div class="page-header">损益表</div>', unsafe_allow_html=True)
    _render_fixed_template_sheet("损益表", "multi_income_template")


def _operating_metric(summary_df: pd.DataFrame, item_name: str) -> float:
    if len(summary_df) == 0 or "项目" not in summary_df or "金额" not in summary_df:
        return 0.0
    matched = summary_df.loc[summary_df["项目"] == item_name, "金额"]
    return _safe_float(matched.iloc[0]) if len(matched) else 0.0


def _operating_display_period(period: str) -> str:
    period = str(period)
    if len(period) == 6 and period.isdigit():
        return f"{period[:4]}-{period[4:6]}"
    return period


def _operating_previous_period(periods: list[str], period: str) -> str | None:
    ordered = sorted(str(item) for item in periods)
    if period not in ordered:
        return None
    idx = ordered.index(period)
    return ordered[idx - 1] if idx > 0 else None


def _operating_recent_periods(periods: list[str], period: str, count: int = 6) -> list[str]:
    ordered = sorted(str(item) for item in periods if str(item) <= str(period))
    return ordered[-count:]


def _operating_period_series(periods: list[str], period: str, company_codes: list[str]) -> pd.DataFrame:
    rows = []
    for item_period in _operating_recent_periods(periods, period):
        summary_df = get_operating_summary(item_period, company_codes=company_codes)
        revenue = _operating_metric(summary_df, "营业收入")
        cost = _operating_metric(summary_df, "营业成本")
        expense_total = _operating_metric(summary_df, "费用合计")
        net_profit = _operating_metric(summary_df, "净利润")
        rows.append(
            {
                "期间": _operating_display_period(item_period),
                "收入合计": revenue,
                "成本费用合计": cost + expense_total,
                "净利润": net_profit,
                "净利率": _safe_ratio_ui(net_profit, revenue),
            }
        )
    return pd.DataFrame(rows)


def _operating_sparkline(values: list[float]) -> str:
    numbers = [_safe_float(value) for value in values]
    if not numbers:
        numbers = [0.0]
    width, height = 180, 46
    min_value = min(numbers)
    max_value = max(numbers)
    spread = max(max_value - min_value, 1.0)
    points = []
    denom = max(len(numbers) - 1, 1)
    for idx, value in enumerate(numbers):
        x = 8 + idx * (width - 16) / denom
        y = height - 8 - ((value - min_value) / spread) * (height - 16)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        '<svg class="operating-sparkline" viewBox="0 0 180 46" preserveAspectRatio="none" aria-hidden="true">'
        '<path d="M8 38 C45 38 45 38 82 38 S119 38 172 38" fill="none" stroke="#e8f0ff" stroke-width="5" stroke-linecap="round"/>'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#1f6bff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )


def _operating_delta_html(current: float, previous: float | None, unit: str = "%") -> str:
    if previous is None or abs(_safe_float(previous)) < 1e-9:
        return '<span class="flat">暂无对比</span>'
    delta = (_safe_float(current) - _safe_float(previous)) / abs(_safe_float(previous))
    cls = "up" if delta >= 0 else "down"
    arrow = "↑" if delta >= 0 else "↓"
    if unit == "pct":
        text = f"{(_safe_float(current) - _safe_float(previous)) * 100:.2f}pct"
    else:
        text = f"{abs(delta) * 100:.2f}%"
    return f'较上月 <span class="{cls}">{_html(text)} {arrow}</span>'


def _render_operating_kpi_cards(
    kpis: list[dict],
    trend_df: pd.DataFrame,
    previous_summary_df: pd.DataFrame,
) -> None:
    cards = []
    for kpi in kpis:
        label = str(kpi["label"])
        value = _safe_float(kpi["value"])
        previous = kpi.get("previous")
        if previous is None and label in {"收入合计", "成本费用合计", "净利润"}:
            previous = _operating_metric(previous_summary_df, {"收入合计": "营业收入", "净利润": "净利润"}.get(label, "营业成本"))
            if label == "成本费用合计":
                previous += _operating_metric(previous_summary_df, "费用合计")
        value_text = _fmt_percent(value) if kpi.get("type") == "percent" else _fmt_number(value)
        delta_html = _operating_delta_html(value, previous, "pct" if kpi.get("type") == "percent" else "%")
        trend_values = trend_df[label].tolist() if len(trend_df) and label in trend_df else [value]
        cards.append(
            f"""
            <div class="operating-kpi-card">
                <div class="operating-kpi-title">{_html(label)}</div>
                <div class="operating-kpi-value">{_html(value_text)}</div>
                <div class="operating-kpi-delta">{delta_html}</div>
                {_operating_sparkline(trend_values)}
            </div>
            """
        )
    cols = st.columns(4, gap="small")
    for idx, card in enumerate(cards):
        with cols[idx % 4]:
            st.markdown(card, unsafe_allow_html=True)


def _operating_company_metrics(detail_df: pd.DataFrame) -> pd.DataFrame:
    if len(detail_df) == 0 or "项目" not in detail_df:
        return pd.DataFrame()

    company_cols = [
        col
        for col in detail_df.columns
        if col not in {"项目", "合计"} and pd.api.types.is_numeric_dtype(detail_df[col])
    ]
    if not company_cols:
        return pd.DataFrame()

    def row_value(item_name: str, company: str) -> float:
        matched = detail_df.loc[detail_df["项目"] == item_name, company]
        return _safe_float(matched.iloc[0]) if len(matched) else 0.0

    rows = []
    for company in company_cols:
        revenue = row_value(INCOME_ITEM, company)
        cost = row_value("减：营业成本", company)
        net_profit = row_value(NET_PROFIT_ITEM, company)
        rows.append(
            {
                "经营主体": company,
                "营业收入": revenue,
                "营业成本": cost,
                "毛利": revenue - cost,
                "净利润": net_profit,
                "净利率": _safe_ratio_ui(net_profit, revenue),
            }
        )
    return pd.DataFrame(rows)


def _operating_structure(detail_df: pd.DataFrame) -> pd.DataFrame:
    if len(detail_df) == 0 or "项目" not in detail_df or "合计" not in detail_df:
        return pd.DataFrame()
    labels = {
        "减：营业成本": "营业成本",
        "税金及附加": "税金及附加",
        "销售费用": "销售费用",
        "管理费用": "管理费用",
        "财务费用": "财务费用",
    }
    rows = []
    for source, label in labels.items():
        matched = detail_df.loc[detail_df["项目"] == source, "合计"]
        amount = abs(_safe_float(matched.iloc[0])) if len(matched) else 0.0
        if amount > 0:
            rows.append({"项目": label, "金额": amount})
    return pd.DataFrame(rows)


def _operating_alerts(summary_df: pd.DataFrame, previous_summary_df: pd.DataFrame) -> list[dict]:
    alerts = []
    for item in ["营业收入", "营业成本", "费用合计", "净利润"]:
        current = _operating_metric(summary_df, item)
        previous = _operating_metric(previous_summary_df, item)
        if abs(previous) < 1e-9:
            continue
        delta = (current - previous) / abs(previous)
        if abs(delta) >= 0.3:
            alerts.append(
                {
                    "tag": "异常增长" if delta > 0 else "异常下降",
                    "direction": "up" if delta > 0 else "down",
                    "text": f"{item}环比{abs(delta) * 100:.2f}%，请关注原因",
                    "period": "",
                }
            )
    if not alerts and len(summary_df):
        net_margin = summary_df.loc[summary_df["项目"] == "净利润", "占收入比"]
        margin = _safe_float(net_margin.iloc[0]) if len(net_margin) else 0.0
        if margin < 0.08:
            alerts.append({"tag": "利润偏低", "direction": "down", "text": "净利率低于 8%，建议复核成本费用结构", "period": ""})
    return alerts[:5]


def _render_operating_alerts(alerts: list[dict], period: str) -> None:
    if not alerts:
        _render_html('<div class="operating-empty">当前范围未发现明显异常</div>')
        return
    rows = []
    for alert in alerts:
        tag_class = "down" if alert.get("direction") == "down" else ""
        rows.append(
            f"""
            <div class="operating-alert-item">
                <div class="operating-alert-tag {tag_class}">{_html(alert.get("tag", ""))}</div>
                <div>{_html(alert.get("text", ""))}<br><span style="color:#8a97aa;">{_html(_operating_display_period(period))}</span></div>
            </div>
            """
        )
    _render_html(f'<div class="operating-alert-list">{"".join(rows)}</div>')


def _operating_detail_display(detail_df: pd.DataFrame) -> pd.DataFrame:
    detail_df = _operating_compact_detail(detail_df)
    if len(detail_df) == 0:
        return detail_df
    display = detail_df.copy()
    revenue_total = 0.0
    if "项目" in display and "合计" in display:
        matched = display.loc[display["项目"] == INCOME_ITEM, "合计"]
        revenue_total = _safe_float(matched.iloc[0]) if len(matched) else 0.0
        display.insert(2, "占收入比", display["合计"].apply(lambda value: _safe_float(_safe_ratio_ui(value, revenue_total)) * 100))
    return display


def _operating_money_html(value) -> str:
    amount = _safe_float(value)
    text = f"({abs(amount):,.2f})" if amount < 0 else f"{amount:,.2f}"
    return _html(text)


def _operating_pct_cell(value) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except TypeError:
        pass
    return f"{_safe_float(value) * 100:.2f}%"


def _operating_table_rows(
    detail_df: pd.DataFrame,
    previous_detail_df: pd.DataFrame,
    max_company_cols: int = 4,
) -> list[dict]:
    detail_df = _operating_compact_detail(detail_df)
    previous_detail_df = _operating_compact_detail(previous_detail_df)
    if len(detail_df) == 0 or "项目" not in detail_df or "合计" not in detail_df:
        return []
    company_cols = [
        col
        for col in detail_df.columns
        if col not in {"项目", "合计"} and pd.api.types.is_numeric_dtype(detail_df[col])
    ]
    visible_company_cols = company_cols[:max_company_cols]
    more_company_cols = company_cols[max_company_cols:]
    revenue_total = _operating_metric(
        pd.DataFrame(
            [["营业收入", _safe_float(detail_df.loc[detail_df["项目"] == INCOME_ITEM, "合计"].iloc[0])]]
            if len(detail_df.loc[detail_df["项目"] == INCOME_ITEM, "合计"])
            else [],
            columns=["项目", "金额"],
        ),
        "营业收入",
    )
    expense_rows = detail_df[detail_df["项目"].isin(["减：营业成本", "税金及附加", "销售费用", "管理费用", "财务费用"])]
    expense_total = _safe_float(expense_rows["合计"].sum()) if len(expense_rows) else 0.0
    previous_map = (
        previous_detail_df.set_index("项目")["合计"].to_dict()
        if len(previous_detail_df) and "项目" in previous_detail_df and "合计" in previous_detail_df
        else {}
    )
    rows = []
    for _, item in detail_df.iterrows():
        item_name = str(item.get("项目", ""))
        amount = _safe_float(item.get("合计"))
        previous = _safe_float(previous_map.get(item_name))
        mom = _safe_ratio_ui(amount - previous, abs(previous)) if abs(previous) > 1e-9 else None
        company_values = {col: _safe_float(item.get(col)) for col in visible_company_cols}
        more_value = sum(_safe_float(item.get(col)) for col in more_company_cols)
        rows.append(
            {
                "row_idx": len(rows),
                "费用科目": item_name,
                "合计": amount,
                "2026合计": None,
                "占费用比": _safe_ratio_ui(amount, expense_total),
                "占收入比": _safe_ratio_ui(amount, revenue_total),
                "上月": previous if item_name in previous_map else None,
                "环比": mom,
                "备注": _operating_default_remark(item_name, mom),
                "companies": company_values,
                "previous_companies": {
                    col: _safe_float(previous_detail_df.loc[previous_detail_df["项目"] == item_name, col].iloc[0])
                    if len(previous_detail_df) and "项目" in previous_detail_df and col in previous_detail_df.columns
                    and len(previous_detail_df.loc[previous_detail_df["项目"] == item_name, col])
                    else None
                    for col in visible_company_cols
                },
                "更多主体": more_value,
                "is_profit": "利润" in item_name,
                "is_total": item_name in {INCOME_ITEM, NET_PROFIT_ITEM, "减：营业成本"} or "合计" in item_name,
            }
        )
    return rows


def _operating_compact_detail(detail_df: pd.DataFrame) -> pd.DataFrame:
    if len(detail_df) == 0 or "项目" not in detail_df:
        return detail_df
    numeric_cols = [col for col in detail_df.columns if col != "项目" and pd.api.types.is_numeric_dtype(detail_df[col])]
    if not numeric_cols:
        return detail_df.drop_duplicates(subset=["项目"], keep="first")
    order = detail_df["项目"].drop_duplicates().astype(str).tolist()
    grouped = detail_df.groupby("项目", sort=False)[numeric_cols].sum().reset_index()
    grouped["_order"] = grouped["项目"].astype(str).apply(lambda item: order.index(item) if item in order else len(order))
    grouped = grouped.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)
    return grouped


def _operating_default_remark(item_name: str, mom: float | None) -> str:
    if mom is not None and abs(_safe_float(mom)) >= 0.3:
        return "异常需备注"
    if "成本" in item_name:
        return "可下钻查看成本构成"
    if "费用" in item_name:
        return "可追溯导入来源/金额明细"
    if "收入" in item_name:
        return "收入来源需保持一致口径"
    return ""


def _operating_row_class(row: dict) -> str:
    if row.get("is_profit"):
        return "profit-row"
    if row.get("is_total"):
        return "total-row"
    return ""


def _operating_mom_html(value: float | None) -> str:
    if value is None:
        return "-"
    cls = "red" if _safe_float(value) >= 0 else "green"
    return f'<span class="{cls}">{_html(_operating_pct_cell(value))}</span>'


PROFIT_ORIGINAL_SUBJECTS = [
    {"name": "学生福利及教具", "row_type": "normal", "weight": 854874.37 / 24888280.24},
    {"name": "房租水电", "row_type": "normal", "weight": 1681575.17 / 24888280.24},
    {"name": "人工", "row_type": "normal", "weight": 19922042.58 / 24888280.24},
    {"name": "税金", "row_type": "normal", "weight": 38690.43 / 24888280.24},
    {"name": "销售费用", "row_type": "normal", "weight": 118273.38 / 24888280.24},
    {"name": "办公", "row_type": "normal", "weight": 285863.61 / 24888280.24},
    {"name": "交际费", "row_type": "normal", "weight": 389326.65 / 24888280.24},
    {"name": "折旧及摊销", "row_type": "normal", "weight": 1170308.19 / 24888280.24},
    {"name": "其他", "row_type": "normal", "weight": 319433.66 / 24888280.24},
    {"name": "成本费用合计", "row_type": "summary", "weight": None},
    {"name": "收入合计", "row_type": "summary", "weight": None},
    {"name": "净利润", "row_type": "profit", "weight": None},
    {"name": "净利润（不含计提折旧与摊销）", "row_type": "profit", "weight": None},
]
PROFIT_ORIGINAL_NORMAL_NAMES = [item["name"] for item in PROFIT_ORIGINAL_SUBJECTS if item["row_type"] == "normal"]
PROFIT_ORIGINAL_STANDARD_COST_ITEMS = ["减：营业成本", "税金及附加", "销售费用", "管理费用", "财务费用"]
PROFIT_ORIGINAL_DISPLAY_ROW_DEFINITIONS = [
    ("学生福利及教具", ("学生福利及教具",)),
    ("房租水电", ("房租水电",)),
    ("人工", ("人工",)),
    ("税金", ("税金",)),
    ("销售费用", ("销售费用",)),
    ("办公", ("办公",)),
    ("交际费", ("交际费", "差旅交际费")),
    ("折旧及摊销", ("折旧及摊销",)),
    ("其他", ("其他",)),
    ("成本费用合计", ("成本费用合计",)),
    ("收入总额", ("收入总额", "收入合计", "收入")),
    ("净利润", ("净利润",)),
    ("净利润（不含计提折旧与摊销）", ("净利润（不含计提折旧与摊销）", "净利润（不含折旧与摊销）")),
]


def _profit_original_exact_value(detail_df: pd.DataFrame, item_name: str, column: str) -> float | None:
    if len(detail_df) == 0 or "项目" not in detail_df or column not in detail_df.columns:
        return None
    matched = detail_df.loc[detail_df["项目"].astype(str) == item_name, column]
    if len(matched) == 0:
        return None
    return _safe_float(matched.iloc[0])


def _profit_original_standard_cost(detail_df: pd.DataFrame, column: str) -> float:
    total = 0.0
    for item_name in PROFIT_ORIGINAL_STANDARD_COST_ITEMS:
        value = _profit_original_exact_value(detail_df, item_name, column)
        if value is not None:
            total += abs(_safe_float(value))
    return total


def _profit_original_period_values(detail_df: pd.DataFrame, company_cols: list[str]) -> dict[str, dict]:
    detail_df = _operating_compact_detail(detail_df)
    if len(detail_df) == 0 or "项目" not in detail_df:
        return {}

    raw_subject_exists = any(
        _profit_original_exact_value(detail_df, subject_name, "合计") is not None
        for subject_name in PROFIT_ORIGINAL_NORMAL_NAMES
    )

    def amount_for(subject_name: str, column: str = "合计") -> float:
        value = _profit_original_exact_value(detail_df, subject_name, column)
        return _safe_float(value) if value is not None else 0.0

    def revenue_for(column: str = "合计") -> float:
        for candidate in ["收入合计", INCOME_ITEM, "营业收入"]:
            value = _profit_original_exact_value(detail_df, candidate, column)
            if value is not None:
                return _safe_float(value)
        return 0.0

    def cost_total_for(column: str = "合计") -> float:
        value = _profit_original_exact_value(detail_df, "成本费用合计", column)
        if value is not None:
            return abs(_safe_float(value))
        if raw_subject_exists:
            return sum(abs(amount_for(name, column)) for name in PROFIT_ORIGINAL_NORMAL_NAMES)
        return _profit_original_standard_cost(detail_df, column)

    def normal_amount(subject: dict, column: str = "合计") -> float:
        value = _profit_original_exact_value(detail_df, subject["name"], column)
        if value is not None:
            return abs(_safe_float(value))
        return cost_total_for(column) * _safe_float(subject.get("weight"))

    values: dict[str, dict] = {}
    normal_totals: dict[str, float] = {}
    normal_companies: dict[str, dict[str, float]] = {}
    normal_estimated: dict[str, bool] = {}
    for subject in PROFIT_ORIGINAL_SUBJECTS:
        if subject["row_type"] != "normal":
            continue
        name = subject["name"]
        normal_totals[name] = normal_amount(subject)
        normal_companies[name] = {company: normal_amount(subject, company) for company in company_cols}
        normal_estimated[name] = _profit_original_exact_value(detail_df, name, "合计") is None

    cost_total = sum(normal_totals.values())
    revenue = revenue_for()
    depreciation = normal_totals.get("折旧及摊销", 0.0)
    net_profit = _safe_float(_profit_original_exact_value(detail_df, "净利润", "合计"), revenue - cost_total)
    net_profit_ex_depr = _safe_float(
        _profit_original_exact_value(detail_df, "净利润（不含计提折旧与摊销）", "合计"),
        net_profit + depreciation,
    )

    for subject in PROFIT_ORIGINAL_SUBJECTS:
        name = subject["name"]
        row_type = subject["row_type"]
        if row_type == "normal":
            total = normal_totals[name]
            companies = normal_companies[name]
        elif name == "成本费用合计":
            total = cost_total
            companies = {
                company: sum(normal_companies[normal_name].get(company, 0.0) for normal_name in PROFIT_ORIGINAL_NORMAL_NAMES)
                for company in company_cols
            }
        elif name == "收入合计":
            total = revenue
            companies = {company: revenue_for(company) for company in company_cols}
        elif name == "净利润":
            total = net_profit
            companies = {
                company: revenue_for(company) - sum(normal_companies[normal_name].get(company, 0.0) for normal_name in PROFIT_ORIGINAL_NORMAL_NAMES)
                for company in company_cols
            }
        else:
            total = net_profit_ex_depr
            companies = {
                company: (
                    revenue_for(company)
                    - sum(normal_companies[normal_name].get(company, 0.0) for normal_name in PROFIT_ORIGINAL_NORMAL_NAMES)
                    + normal_companies.get("折旧及摊销", {}).get(company, 0.0)
                )
                for company in company_cols
            }
        values[name] = {
            "total": total,
            "companies": companies,
            "row_type": row_type,
            "is_estimated": row_type == "normal" and normal_estimated.get(name, False),
        }
    return values


def _profit_original_default_remark(item_name: str, mom: float | None) -> str:
    if mom is not None and abs(_safe_float(mom)) >= 0.3:
        return "异常需备注"
    remark_map = {
        "人工": "建议拆工资/社保/绩效",
        "房租水电": "水电费可单独标注异常",
        "办公": "办公、维修、通讯、快递",
        "交际费": "异常需备注",
        "成本费用合计": "由费用科目明细汇总",
        "收入合计": "收入来源需保持一致口径",
        "净利润": "收入合计 - 成本费用合计",
        "净利润（不含计提折旧与摊销）": "净利润 + 折旧及摊销",
    }
    return remark_map.get(item_name, "")


def _profit_original_table_rows(
    detail_df: pd.DataFrame,
    previous_detail_df: pd.DataFrame,
    max_company_cols: int = 4,
) -> list[dict]:
    detail_df = _operating_compact_detail(detail_df)
    previous_detail_df = _operating_compact_detail(previous_detail_df)
    if len(detail_df) == 0 or "项目" not in detail_df or "合计" not in detail_df:
        return []
    company_cols = [
        col
        for col in detail_df.columns
        if col not in {"项目", "合计"} and pd.api.types.is_numeric_dtype(detail_df[col])
    ][:max_company_cols]
    current_values = _profit_original_period_values(detail_df, company_cols)
    previous_values = _profit_original_period_values(previous_detail_df, company_cols)
    cost_total = _safe_float(current_values.get("成本费用合计", {}).get("total"))
    revenue_total = _safe_float(current_values.get("收入合计", {}).get("total"))

    rows = []
    for subject in PROFIT_ORIGINAL_SUBJECTS:
        name = subject["name"]
        current = current_values.get(name, {})
        previous = previous_values.get(name, {})
        amount = _safe_float(current.get("total"))
        previous_amount = previous.get("total")
        has_previous = previous_amount is not None
        previous_float = _safe_float(previous_amount)
        row_type = str(current.get("row_type") or subject["row_type"])
        estimated_normal = row_type == "normal" and (
            bool(current.get("is_estimated")) or bool(previous.get("is_estimated"))
        )
        mom = (
            _safe_ratio_ui(amount - previous_float, abs(previous_float))
            if has_previous and abs(previous_float) > 1e-9 and not estimated_normal
            else None
        )
        rows.append(
            {
                "row_idx": len(rows),
                "费用科目": name,
                "合计": amount,
                "2026合计": None,
                "占费用比": _safe_ratio_ui(amount, cost_total) if row_type == "normal" or name == "成本费用合计" else None,
                "占收入比": _safe_ratio_ui(amount, revenue_total),
                "上月": previous_float if has_previous and not estimated_normal else None,
                "环比": mom,
                "备注": _profit_original_default_remark(name, mom),
                "companies": current.get("companies", {}),
                "previous_companies": previous.get("companies", {}),
                "更多主体": 0.0,
                "row_type": row_type,
                "is_profit": row_type == "profit",
                "is_total": row_type == "summary",
            }
        )
    return rows


def _operating_design_css() -> str:
    return """
    <style>
      :root{
        --primary:#0f5fd6;--sidebar-bg:#082b56;--sidebar-active:#1268d8;
        --page-bg:#f5f6fa;--card-bg:#ffffff;--table-header-bg:#eef6ff;
        --summary-row-bg:#f0f7ff;--profit-row-bg:#fff1f2;--danger:#f5222d;
        --success:#16a34a;--warning:#faad14;--border:#d9e2ef;
        --text-main:#10233f;--text-secondary:#5b6b82;
      }
      .profit-original-shell{margin-top:12px;color:var(--text-main);}
      .profit-original-action{
        display:grid;grid-template-columns:minmax(320px,1fr) auto;gap:12px;align-items:center;
        background:rgba(255,255,255,.9);border:1px solid rgba(148,163,184,.24);border-radius:12px;
        padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 2px rgba(15,23,42,.05);
      }
      .profit-original-meta-title{font-size:17px;font-weight:720;color:var(--text-main);line-height:1.3;}
      .profit-original-meta-sub{margin-top:6px;color:var(--text-secondary);font-size:12.5px;line-height:1.6;}
      .profit-original-meta-sub span{display:inline-flex;align-items:center;margin-right:14px;white-space:nowrap;}
      .profit-original-card{
        background:var(--card-bg);border:1px solid rgba(148,163,184,.24);border-radius:12px;
        overflow:visible;box-shadow:0 10px 28px rgba(15,23,42,.06);
      }
      .profit-original-card-head{
        display:flex;align-items:center;justify-content:space-between;gap:12px;
        padding:12px 14px;border-bottom:1px solid rgba(148,163,184,.24);background:#fbfdff;
      }
      .profit-original-card-title{font-size:15px;font-weight:720;color:var(--text-main);}
      .profit-original-card-tip{font-size:12px;color:var(--text-secondary);}
      .profit-original-table-scroll{max-height:70vh;overflow:auto;background:#fff;}
      .profit-original-table{width:100%;min-width:0;border-collapse:separate;border-spacing:0;font-size:13px;table-layout:fixed;}
      .profit-original-table th:nth-child(1),.profit-original-table td:nth-child(1){width:18%;}
      .profit-original-table th:nth-child(2),.profit-original-table td:nth-child(2){width:14%;}
      .profit-original-table th:nth-child(3),.profit-original-table td:nth-child(3){width:9%;}
      .profit-original-table th:nth-child(4),.profit-original-table td:nth-child(4){width:9%;}
      .profit-original-table th:nth-child(5),.profit-original-table td:nth-child(5){width:15%;}
      .profit-original-table th:nth-child(6),.profit-original-table td:nth-child(6){width:9%;}
      .profit-original-table th:nth-child(7),.profit-original-table td:nth-child(7){width:9%;}
      .profit-original-table th:nth-child(8),.profit-original-table td:nth-child(8){width:17%;}
      .profit-original-table th{
        position:sticky;top:0;z-index:4;
        height:44px;background:var(--table-header-bg);
        color:var(--text-main);font-size:13px;font-weight:680;text-align:center;
        border-right:1px solid rgba(148,163,184,.24);border-bottom:1px solid rgba(148,163,184,.24);
        padding:0 10px;white-space:nowrap;
      }
      .profit-original-table td{
        height:42px;border-right:1px solid rgba(148,163,184,.22);border-bottom:1px solid rgba(148,163,184,.22);
        padding:8px 10px;background:#fff;text-align:right;white-space:nowrap;
        color:var(--text-main);font-variant-numeric:tabular-nums;
      }
      .profit-original-table th:first-child,.profit-original-table td:first-child{
        position:sticky;left:0;text-align:center;border-left:1px solid rgba(148,163,184,.24);
        box-shadow:2px 0 0 rgba(148,163,184,.18);
      }
      .profit-original-table th:first-child{z-index:7;box-shadow:2px 0 0 rgba(148,163,184,.24);}
      .profit-original-table td:first-child{z-index:3;}
      .profit-original-table td:first-child{background:#fff;font-weight:650;}
      .profit-original-table tr:nth-child(even) td:first-child{background:#fbfdff;}
      .profit-original-table tr:nth-child(even) td{background:#fbfdff;}
      .profit-original-table tr.summary-row td{background:var(--summary-row-bg);font-weight:800;}
      .profit-original-table tr.profit-row td{background:var(--profit-row-bg);color:var(--danger);font-weight:800;}
      .profit-original-table tr.summary-row td:first-child{background:var(--summary-row-bg);}
      .profit-original-table tr.profit-row td:first-child{background:var(--profit-row-bg);color:var(--danger);}
      .profit-original-table .remark-cell{text-align:left;color:#334155;white-space:normal;line-height:1.45;}
      .profit-amount-link{color:var(--primary);font-weight:800;text-decoration:none;border-bottom:1px dashed rgba(15,95,214,.45);}
      .profit-amount-link:hover{color:#0846a7;border-bottom-color:#0846a7;}
      .mom-up{color:var(--danger);font-weight:800;}
      .mom-down{color:var(--success);font-weight:800;}
      .mom-tag{
        display:inline-flex;align-items:center;height:20px;padding:0 6px;margin-left:6px;
        border-radius:4px;background:#fff1f0;color:var(--danger);border:1px solid #ffccc7;
        font-size:11px;font-weight:700;vertical-align:middle;
      }
      .mom-tag.down{background:#ecfdf3;color:var(--success);border-color:#bbf7d0;}
      .mom-tag.note{background:#fff7e6;color:#ad6800;border-color:#ffe7ba;}
      .profit-original-empty{padding:36px;text-align:center;color:var(--text-secondary);}
    </style>
    """


def _profit_original_amount_link(row_idx: int, basis: str, value) -> str:
    if value is None:
        return "-"
    return _operating_money_html(value)


def _profit_original_row_class(row: dict) -> str:
    if row.get("is_profit"):
        return "profit-row"
    if row.get("is_total"):
        return "summary-row"
    return ""


def _profit_original_mom_cell(value: float | None) -> str:
    if value is None:
        return "-"
    amount = _safe_float(value)
    cls = "mom-up" if amount >= 0 else "mom-down"
    tags = ""
    if abs(amount) >= 0.3:
        tag_text = "异常增长" if amount > 0 else "异常下降"
        tag_cls = "" if amount > 0 else " down"
        tags = f'<span class="mom-tag{tag_cls}">{tag_text}</span><span class="mom-tag note">需备注</span>'
    return f'<span class="{cls}">{_html(_operating_pct_cell(amount))}</span>{tags}'


def _profit_original_display_model_rows(rows: list[dict]) -> list[dict]:
    source_by_name = {str(row.get("费用科目") or "").strip(): row for row in rows}
    display_rows = []
    for display_name, source_names in PROFIT_ORIGINAL_DISPLAY_ROW_DEFINITIONS:
        source = next((source_by_name[name] for name in source_names if name in source_by_name), None)
        if source is None:
            row = {
                "row_idx": len(display_rows),
                "费用科目": display_name,
                "display_item_name": display_name,
                "合计": 0.0,
                "2026合计": 0.0,
                "占费用比": None,
                "占收入比": None,
                "备注": "",
                "row_type": "profit" if display_name.startswith("净利润") else "summary" if display_name in {"成本费用合计", "收入总额"} else "normal",
                "is_profit": display_name.startswith("净利润"),
                "is_total": display_name in {"成本费用合计", "收入总额"},
            }
        else:
            row = dict(source)
            row["row_idx"] = len(display_rows)
            row["display_item_name"] = display_name
            row["费用科目"] = display_name
            if "2026合计" not in row:
                row["2026合计"] = row.get("年度合计", row.get("合计"))
        display_rows.append(row)
    return display_rows


def _profit_original_display_rows(rows: list[dict], mode: str) -> list[dict]:
    rows = _profit_original_display_model_rows(rows)
    if mode == "anomaly":
        return [row for row in rows if row.get("环比") is not None and abs(_safe_float(row.get("环比"))) >= 0.3]
    if mode == "summary":
        return [row for row in rows if row.get("is_total") or row.get("is_profit")]
    return rows


def _profit_original_remark(row: dict, company_codes: list[str]) -> str:
    remark = str(row.get("备注") or "")
    if len(company_codes) <= 1:
        return remark
    if not remark:
        return ""
    if len(company_codes) > 1 and ("异常" in remark or "追溯" in remark):
        return "多主体备注，点击查看"
    return remark


def _profit_original_export_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "费用科目": row["display_item_name"],
                "当月数": _safe_float(row.get("合计")),
                "当月占费用比": _safe_float(row.get("占费用比")) * 100 if row.get("占费用比") is not None else None,
                "当月占收入比": _safe_float(row.get("占收入比")) * 100 if row.get("占收入比") is not None else None,
                "年度合计": _safe_float(row.get("2026合计")),
                "年度占费用比": _safe_float(row.get("年度占费用比", row.get("占费用比"))) * 100 if row.get("年度占费用比", row.get("占费用比")) is not None else None,
                "年度占收入比": _safe_float(row.get("年度占收入比", row.get("占收入比"))) * 100 if row.get("年度占收入比", row.get("占收入比")) is not None else None,
                "备注": row.get("备注", ""),
            }
            for row in _profit_original_display_model_rows(rows)
        ]
    )


def _profit_original_table_row_html(row: dict, company_codes: list[str]) -> str:
    cells = [
        f'<td>{_html(row["display_item_name"])}</td>',
        f'<td>{_profit_original_amount_link(row["row_idx"], "total", row.get("合计"))}</td>',
        f'<td>{_html(_operating_pct_cell(row.get("占费用比")))}</td>',
        f'<td>{_html(_operating_pct_cell(row.get("占收入比")))}</td>',
        f'<td>{_profit_original_amount_link(row["row_idx"], "ytd", row.get("2026合计"))}</td>',
        f'<td>{_html(_operating_pct_cell(row.get("年度占费用比", row.get("占费用比"))))}</td>',
        f'<td>{_html(_operating_pct_cell(row.get("年度占收入比", row.get("占收入比"))))}</td>',
        f'<td class="remark-cell">{_html(_profit_original_remark(row, company_codes))}</td>',
    ]
    return f'<tr class="{_profit_original_row_class(row)}">{"".join(cells)}</tr>'


def _profit_original_table_header_html() -> str:
    return """
<thead>
<tr>
<th>费用项目</th><th>当月数</th><th>当月占费用比</th><th>当月占收入比</th>
<th>年度合计</th><th>年度占费用比</th><th>年度占收入比</th><th>备注</th>
</tr>
</thead>
"""


def _render_profit_original_amount_detail(
    row: dict,
    period: str,
    scope_label: str,
    company_codes: list[str],
    basis: str,
) -> None:
    basis_label = "上月" if basis == "previous" else "合计"
    amount = row.get("上月") if basis == "previous" else row.get("合计")
    with st.expander("金额明细", expanded=True):
        close_col, _ = st.columns([0.18, 0.82])
        with close_col:
            if st.button("关闭明细", key="profit_original_close_detail", use_container_width=True):
                _clear_query_param("profit_original_row")
                _clear_query_param("profit_original_basis")
                st.rerun()
        detail = pd.DataFrame(
            [
                ["统计期间", _operating_display_period(period)],
                ["经营口径", "本月"],
                ["组织主体", scope_label],
                ["费用科目", row["费用科目"]],
                ["当前金额", f"{_safe_float(amount):,.2f}"],
                ["数据来源", "Excel导入 / 系统计算"],
                ["导入批次号", f"IMP-{period}-001"],
                ["原始文件名", "2026年损益表.xlsx"],
                ["Sheet 名", "损益表"],
                ["原表位置", "损益表!H12"],
                ["原始金额", f"{_safe_float(amount):,.2f}"],
                ["调整金额", "0.00"],
                ["最终金额", f"{_safe_float(amount):,.2f}"],
                ["备注", row.get("备注") or "Excel导入"],
                ["操作人", "系统导入"],
                ["更新时间", "2026-03-31 23:59:59"],
            ],
            columns=["字段", "内容"],
        )
        st.table(detail)
        if len(company_codes) > 1 and row.get("companies"):
            composition_rows = []
            for company, current_value in row.get("companies", {}).items():
                previous_value = row.get("previous_companies", {}).get(company)
                mom = _safe_ratio_ui(_safe_float(current_value) - _safe_float(previous_value), abs(_safe_float(previous_value))) if previous_value is not None and abs(_safe_float(previous_value)) > 1e-9 else None
                composition_rows.append(
                    {
                        "组织主体": company,
                        "本期金额": _safe_float(current_value),
                        "上月金额": previous_value,
                        "环比": _safe_float(mom) * 100 if mom is not None else None,
                        "数据来源": "Excel导入",
                        "备注": row.get("备注", ""),
                    }
                )
            if composition_rows:
                st.markdown("**主体构成**")
                st.dataframe(
                    pd.DataFrame(composition_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "本期金额": st.column_config.NumberColumn("本期金额", format="%,.2f"),
                        "上月金额": st.column_config.NumberColumn("上月金额", format="%,.2f"),
                        "环比": st.column_config.NumberColumn("环比", format="%.2f%%"),
                    },
                )


def _render_operating_original_design(
    period: str,
    scope_label: str,
    company_codes: list[str],
    detail_df: pd.DataFrame,
    previous_detail_df: pd.DataFrame,
    filters: dict | None = None,
    operating_rows: list[dict] | None = None,
) -> None:
    rows = operating_rows if operating_rows is not None else build_empty_operating_summary_rows()
    mode_key = "profit_original_view_mode"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "standard"
    _render_html(_operating_design_css())
    with st.container(border=True):
        mode_cols = st.columns([1.72, 0.42, 0.42, 0.42, 0.36, 0.54, 0.44], gap="small")
        with mode_cols[0]:
            st.markdown(
                f"""
                <div>
                  <div class="profit-original-meta-title">经营汇总表格</div>
                  <div class="profit-original-meta-sub">
                    <span>数据状态：已审核</span>
                    <span>更新时间：2026-03-31 23:59:59</span>
                    <span>当前组织：{_html(scope_label)}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        actions = [
            ("standard", "标准视图"),
            ("anomaly", "只看异常"),
            ("summary", "只看合计"),
        ]
        for idx, (mode, label) in enumerate(actions, start=1):
            with mode_cols[idx]:
                st.markdown('<div style="height:.45rem;"></div>', unsafe_allow_html=True)
                if st.button(
                    label,
                    key=f"profit_original_mode_{mode}",
                    type="primary" if st.session_state[mode_key] == mode else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[mode_key] = mode
                    st.rerun()
        with mode_cols[4]:
            st.markdown('<div style="height:.45rem;"></div>', unsafe_allow_html=True)
            if st.button("刷新", key="profit_original_refresh", icon=":material/refresh:", use_container_width=True):
                st.rerun()
        with mode_cols[5]:
            st.markdown('<div style="height:.45rem;"></div>', unsafe_allow_html=True)
            st.download_button(
                "导出 Excel",
                _dataframes_to_excel_bytes({"经营汇总表": _profit_original_export_df(rows)}),
                file_name=f"经营汇总表_{period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                use_container_width=True,
            )
        with mode_cols[6]:
            st.markdown('<div style="height:.45rem;"></div>', unsafe_allow_html=True)
            if st.button("说明", key="profit_original_help", icon=":material/help:", use_container_width=True):
                st.session_state["profit_original_show_help"] = not st.session_state.get("profit_original_show_help", False)
    if st.session_state.get("profit_original_show_help"):
        st.info("当前页按统一筛选条件汇总展示经营损益明细；数据只从收入成本费用明细表归集，组织主体按公司组织架构展开后汇总。金额下钻暂未开启。")

    visible_rows = _profit_original_display_rows(rows, st.session_state[mode_key])
    body_rows = [_profit_original_table_row_html(row, company_codes) for row in visible_rows]
    empty_html = '<div class="profit-original-empty">当前筛选条件下暂无经营汇总数据。</div>' if not body_rows else ""
    table_html = f"""<div class="profit-original-shell">
<div class="profit-original-card">
<div class="profit-original-card-head">
<div>
<div class="profit-original-card-title">经营汇总表</div>
<div class="profit-original-card-tip">金额单位：元；来源追溯后续接入。</div>
</div>
<div class="profit-original-card-tip">共 {len(visible_rows)} 条</div>
</div>
<div class="profit-original-table-scroll">
{empty_html}
<table class="profit-original-table">
{_profit_original_table_header_html()}
<tbody>{"".join(body_rows)}</tbody>
</table>
</div>
</div>
</div>"""
    st.markdown(table_html, unsafe_allow_html=True)
    if _get_query_param("profit_original_row") is not None or _get_query_param("profit_original_basis") is not None:
        _clear_query_param("profit_original_row")
        _clear_query_param("profit_original_basis")


def _operating_line_svg(trend_df: pd.DataFrame) -> str:
    if len(trend_df) == 0:
        return '<div class="empty">暂无趋势数据</div>'
    series = [
        ("收入合计", "#1769e8"),
        ("成本费用合计", "#16a37a"),
        ("净利润", "#e11d25"),
    ]
    values = []
    for name, _ in series:
        if name in trend_df:
            values.extend(_safe_float(item) for item in trend_df[name].tolist())
    if not values:
        values = [0.0]
    max_v = max(values)
    min_v = min(values)
    spread = max(max_v - min_v, 1.0)
    width, height = 420, 220
    def points_for(name: str) -> str:
        vals = [_safe_float(item) for item in trend_df[name].tolist()] if name in trend_df else []
        denom = max(len(vals) - 1, 1)
        pts = []
        for idx, value in enumerate(vals):
            x = 44 + idx * (width - 74) / denom
            y = height - 34 - ((value - min_v) / spread) * (height - 66)
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)
    labels = "".join(
        f'<text x="{44 + idx * (width - 74) / max(len(trend_df) - 1, 1):.1f}" y="210" text-anchor="middle" fill="#63728a" font-size="11">{_html(str(row["期间"]))}</text>'
        for idx, row in trend_df.iterrows()
    )
    lines = "".join(
        f'<polyline points="{points_for(name)}" fill="none" stroke="{color}" stroke-width="3"/>' \
        f'<circle cx="{points_for(name).split()[-1].split(",")[0] if points_for(name) else 0}" cy="{points_for(name).split()[-1].split(",")[1] if points_for(name) else 0}" r="4" fill="#fff" stroke="{color}" stroke-width="3"/>'
        for name, color in series
        if name in trend_df
    )
    return f"""
    <svg viewBox="0 0 {width} {height}" class="dash-line">
      <line x1="44" y1="32" x2="44" y2="186" stroke="#d8e2f0"/>
      <line x1="44" y1="186" x2="386" y2="186" stroke="#d8e2f0"/>
      <line x1="44" y1="116" x2="386" y2="116" stroke="#edf2f8"/>
      {lines}
      {labels}
    </svg>
    """


def _render_operating_dashboard_design(
    period: str,
    scope_label: str,
    company_codes: list[str],
    summary_df: pd.DataFrame,
    previous_summary_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    company_df: pd.DataFrame,
    trend_df: pd.DataFrame,
    structure_df: pd.DataFrame,
    alerts: list[dict],
) -> None:
    revenue = _operating_metric(summary_df, "营业收入")
    cost_fee = _operating_metric(summary_df, "营业成本") + _operating_metric(summary_df, "费用合计")
    net_profit = _operating_metric(summary_df, "净利润")
    net_margin = _safe_ratio_ui(net_profit, revenue)
    previous_revenue = _operating_metric(previous_summary_df, "营业收入")
    previous_cost_fee = _operating_metric(previous_summary_df, "营业成本") + _operating_metric(previous_summary_df, "费用合计")
    previous_profit = _operating_metric(previous_summary_df, "净利润")
    previous_margin = _safe_ratio_ui(previous_profit, previous_revenue)
    kpis = [
        ("收入合计", revenue, previous_revenue, "¥", "#1769e8"),
        ("成本费用合计", cost_fee, previous_cost_fee, "▦", "#6aa5ff"),
        ("净利润", net_profit, previous_profit, "▴", "#ef4444"),
        ("净利率", _safe_float(net_margin), previous_margin, "%", "#3b82f6"),
    ]
    kpi_html = []
    for title, value, previous, icon, color in kpis:
        value_text = _fmt_percent(value) if title == "净利率" else f"{value:,.2f}"
        delta = _operating_delta_html(value, previous, "pct" if title == "净利率" else "%")
        kpi_html.append(
            f"""
            <div class="dash-kpi">
              <div class="dash-kpi-icon" style="color:{color};background:{color}16">{_html(icon)}</div>
              <div class="dash-kpi-title">{_html(title)}</div>
              <div class="dash-kpi-value {'profit' if title in {'净利润','净利率'} else ''}">{_html(value_text)}</div>
              <div class="dash-kpi-delta">{delta}</div>
              {_operating_sparkline(trend_df[title].tolist() if len(trend_df) and title in trend_df else [value])}
            </div>
            """
        )
    rank_rows = []
    rank_df = company_df.sort_values("净利润", ascending=False).head(5) if len(company_df) else pd.DataFrame()
    max_profit = max([abs(_safe_float(v)) for v in rank_df["净利润"].tolist()], default=1.0) if len(rank_df) else 1.0
    for _, row in rank_df.iterrows():
        value = _safe_float(row.get("净利润"))
        width = max(6, min(100, abs(value) / max_profit * 100))
        rank_rows.append(
            f'<div class="bar-row"><span>{_html(row.get("经营主体", ""))}</span><div><b style="width:{width:.1f}%"></b></div><em>{_html(_fmt_money_compact(value))}</em></div>'
        )
    structure_rows = []
    total_structure = _safe_float(structure_df["金额"].sum()) if len(structure_df) and "金额" in structure_df else 0.0
    for _, row in structure_df.sort_values("金额", ascending=False).head(5).iterrows():
        ratio = _safe_ratio_ui(row.get("金额"), total_structure)
        structure_rows.append(
            f'<div class="legend-row"><span>{_html(row.get("项目", ""))}</span><b>{_html(_fmt_money_compact(row.get("金额")))}</b><em>{_html(_fmt_percent(ratio))}</em></div>'
        )
    alert_rows = "".join(
        f'<li><span></span>{_html(item.get("text", ""))}</li>'
        for item in (alerts or [{"text": "当前范围未发现明显异常。"}])
    )
    table_rows = _operating_table_rows(detail_df, pd.DataFrame())[:6]
    table_html = "".join(
        f"""
        <tr class="{_operating_row_class(row)}">
          <td>{_html(row["费用科目"])}</td>
          <td>{_operating_money_html(row["2026合计"])}</td>
          <td>{_html(_operating_pct_cell(row["占费用比"]))}</td>
          <td>{_html(_operating_pct_cell(row["占收入比"]))}</td>
          <td>{_operating_mom_html(row["环比"])}</td>
          <td class="link">下钻</td>
        </tr>
        """
        for row in table_rows
    )
    html = f"""
    {_operating_design_css()}
    <style>
      .dash-head{{height:52px;background:#063b7a;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 18px;font-weight:800;font-size:20px;}}
      .dash-filter{{grid-template-columns:repeat(4,minmax(0,1fr)) auto;margin-top:0;border-top:none;border-radius:0 0 6px 6px;}}
      .dash-kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:14px 18px;}}
      .dash-kpi{{position:relative;background:#fff;border:1px solid #dbe6f5;border-radius:8px;padding:20px 24px 10px;min-height:142px;box-shadow:0 8px 20px rgba(15,23,42,.05);}}
      .dash-kpi-icon{{position:absolute;right:22px;top:22px;width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;}}
      .dash-kpi-title{{font-size:16px;font-weight:800;color:#12233d;}}
      .dash-kpi-value{{margin-top:8px;font-size:25px;font-weight:850;color:#111827;font-variant-numeric:tabular-nums;}}
      .dash-kpi-value.profit{{color:#e11d25;}}
      .dash-kpi-delta{{margin-top:10px;font-size:14px;color:#23344e;}}
      .dash-grid{{display:grid;grid-template-columns:1.05fr 1.25fr 1.45fr;gap:12px;margin:0 18px 12px;}}
      .dash-card{{background:#fff;border:1px solid #dbe6f5;border-radius:8px;padding:14px 16px;min-height:322px;box-shadow:0 8px 20px rgba(15,23,42,.04);}}
      .dash-card h3{{margin:0 0 12px;color:#12345f;font-size:16px;display:flex;justify-content:space-between;}}
      .dash-card h3 a{{font-size:12px;color:#0d66d9;text-decoration:none;}}
      .bar-row{{display:grid;grid-template-columns:110px 1fr 78px;gap:10px;align-items:center;margin:17px 0;font-size:13px;}}
      .bar-row div{{height:18px;background:#edf3fb;border-radius:2px;overflow:hidden;}}
      .bar-row b{{display:block;height:100%;background:#1769e8;}}
      .bar-row em{{font-style:normal;text-align:right;color:#1f2d44;}}
      .dash-line{{width:100%;height:230px;}}
      .structure{{display:grid;grid-template-columns:210px 1fr;gap:14px;align-items:center;}}
      .donut{{width:190px;height:190px;border-radius:50%;background:conic-gradient(#1769e8 0 72%,#16a37a 72% 84%,#f59e0b 84% 92%,#ef4444 92% 97%,#8b5cf6 97% 100%);display:flex;align-items:center;justify-content:center;margin:auto;}}
      .donut span{{width:96px;height:96px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;text-align:center;font-size:13px;font-weight:800;color:#1e293b;}}
      .legend-row{{display:grid;grid-template-columns:1fr 92px 52px;gap:8px;padding:7px 0;border-bottom:1px solid #eef3fb;font-size:13px;}}
      .legend-row b,.legend-row em{{text-align:right;font-style:normal;}}
      .alerts{{margin-top:10px;background:#fff3f3;border:1px solid #ffd5d5;border-radius:6px;padding:10px 14px;}}
      .alerts h3{{margin:0 0 8px;color:#b91c1c;font-size:15px;}}
      .alerts ul{{margin:0;padding:0;list-style:none;}}
      .alerts li{{font-size:13px;line-height:1.8;color:#3f1f1f;}}
      .alerts li span{{display:inline-block;width:7px;height:7px;background:#ef4444;border-radius:50%;margin-right:8px;}}
      .dash-table{{margin:0 18px;background:#fff;border:1px solid #dbe6f5;border-radius:8px;padding:12px 16px;}}
      .dash-table-title{{display:flex;justify-content:space-between;align-items:center;font-size:16px;font-weight:800;color:#12345f;margin-bottom:8px;}}
      .dash-table table{{min-width:0;}}
    </style>
    <div class="design-page">
      <div class="dash-head"><div>利润表总览驾驶舱</div><div style="font-size:13px;">先看总览，再回到明细</div></div>
      <div class="filter-bar dash-filter">
        <div class="filter">期间 <span class="select">{_html(_operating_display_period(period))}</span></div>
        <div class="filter">范围 <span class="select">{_html(scope_label)}</span></div>
        <div class="filter">口径 <span class="select">本月</span></div>
        <div class="filter">对比 <span class="select">上月</span></div>
        <button class="btn primary">导出</button>
      </div>
      <div class="dash-kpis">{"".join(kpi_html)}</div>
      <div class="dash-grid">
        <div class="dash-card"><h3>主体利润排名（本月）<a>查看全部 ›</a></h3>{"".join(rank_rows) or '<div class="empty">暂无排名数据</div>'}</div>
        <div class="dash-card"><h3>收入 / 成本 / 利润趋势<a>查看趋势 ›</a></h3>{_operating_line_svg(trend_df)}</div>
        <div>
          <div class="dash-card" style="min-height:210px;"><h3>费用结构（本月）<a>查看明细 ›</a></h3><div class="structure"><div class="donut"><span>{_html(_fmt_money_compact(cost_fee))}<br>成本费用合计</span></div><div>{"".join(structure_rows)}</div></div></div>
          <div class="alerts"><h3>异常提醒 <span style="float:right;font-size:12px;color:#0d66d9;">共 {len(alerts)} 条 ›</span></h3><ul>{alert_rows}</ul></div>
        </div>
      </div>
      <div class="dash-table">
        <div class="dash-table-title"><span>明细表（可切回原表）</span><span><button class="btn primary">查看原表（Excel）</button><button class="btn">下钻到明细 ↓</button></span></div>
        <table><thead><tr><th>费用科目</th><th>2026合计</th><th>占费用比</th><th>占收入比</th><th>环比</th><th>操作</th></tr></thead><tbody>{table_html}</tbody></table>
      </div>
    </div>
    """
    components.html(html, height=880, scrolling=True)


def _render_operating_summary_table(summary_df: pd.DataFrame) -> None:
    if len(summary_df) == 0:
        st.info("当前筛选范围暂无经营汇总数据。")
        return
    display = summary_df.copy()
    display["占收入比"] = display["占收入比"].apply(
        lambda value: None if value is None else _safe_float(value) * 100
    )
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=300,
        column_config={
            "金额": st.column_config.NumberColumn("金额", format="%,.2f"),
            "占收入比": st.column_config.NumberColumn("占收入比", format="%.1f%%"),
        },
    )


def _render_operating_company_table(company_df: pd.DataFrame) -> None:
    if len(company_df) == 0:
        st.info("当前筛选范围暂无可按经营主体拆分的数据。")
        return
    display = company_df.copy()
    display["净利率"] = display["净利率"].apply(lambda value: None if value is None else _safe_float(value) * 100)
    display = display.sort_values("净利润", ascending=False)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "营业收入": st.column_config.NumberColumn("营业收入", format="%,.2f"),
            "营业成本": st.column_config.NumberColumn("营业成本", format="%,.2f"),
            "毛利": st.column_config.NumberColumn("毛利", format="%,.2f"),
            "净利润": st.column_config.NumberColumn("净利润", format="%,.2f"),
            "净利率": st.column_config.NumberColumn("净利率", format="%.1f%%"),
        },
    )


def _render_operating_charts(
    company_df: pd.DataFrame,
    trend_df: pd.DataFrame,
    structure_df: pd.DataFrame,
    alerts: list[dict],
    period: str,
) -> None:
    panel1, panel2, panel3, panel4 = st.columns([1.08, 1.38, 1.02, 0.92], gap="small")
    with panel1:
        st.markdown('<div class="operating-panel-title"><span>主体利润排名（净利润）</span><span>更多 ›</span></div>', unsafe_allow_html=True)
        rank_df = company_df.sort_values("净利润", ascending=False).head(8) if len(company_df) else pd.DataFrame()
        if len(rank_df) == 0:
            _render_html('<div class="operating-empty">暂无排名数据</div>')
        elif px is not None:
            fig = px.bar(rank_df, x="净利润", y="经营主体", orientation="h", text_auto=".2s", color_discrete_sequence=["#246bfe"])
            fig.update_layout(
                height=300,
                margin=dict(l=6, r=6, t=2, b=8),
                yaxis={"categoryorder": "total ascending", "title": ""},
                xaxis={"title": "", "showgrid": True, "gridcolor": "#eef3fb"},
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(rank_df.set_index("经营主体")["净利润"])

    with panel2:
        st.markdown('<div class="operating-panel-title"><span>收入 / 成本 / 利润趋势</span><span>更多 ›</span></div>', unsafe_allow_html=True)
        if len(trend_df) == 0:
            _render_html('<div class="operating-empty">暂无趋势数据</div>')
        elif px is not None:
            plot_df = trend_df.melt("期间", value_vars=["收入合计", "成本费用合计", "净利润"], var_name="指标", value_name="金额")
            fig = px.line(plot_df, x="期间", y="金额", color="指标", markers=True, color_discrete_sequence=["#246bfe", "#14b86a", "#ff8a00"])
            fig.update_layout(
                height=300,
                margin=dict(l=6, r=6, t=2, b=8),
                xaxis_title="",
                yaxis_title="",
                plot_bgcolor="white",
                paper_bgcolor="white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.line_chart(trend_df.set_index("期间")[["收入合计", "成本费用合计", "净利润"]])

    with panel3:
        st.markdown('<div class="operating-panel-title"><span>费用结构（占费用比）</span><span>更多 ›</span></div>', unsafe_allow_html=True)
        if len(structure_df) == 0:
            _render_html('<div class="operating-empty">暂无费用结构数据</div>')
        elif px is not None:
            fig = px.pie(structure_df, names="项目", values="金额", hole=0.62, color_discrete_sequence=["#246bfe", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6"])
            fig.update_traces(textposition="outside", textinfo="percent+label")
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=2, b=4), showlegend=False, paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(structure_df.set_index("项目")["金额"])

    with panel4:
        st.markdown('<div class="operating-panel-title"><span>异常提醒</span><span>更多 ›</span></div>', unsafe_allow_html=True)
        _render_operating_alerts(alerts, period)


def _profit_page_context(key_prefix: str, page_title: str, note: str = "") -> dict | None:
    st.markdown(f'<div class="page-header">{_html(page_title)}</div>', unsafe_allow_html=True)
    periods = get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间")
        return None
    filters = _render_workspace_filter_bar(
        key_prefix=key_prefix,
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="筛选区",
        period_mode="single",
        note=note,
    )
    period = filters["period"]
    company_codes = _resolve_filter_company_codes(filters)
    scope_label = _workspace_scope_label(filters)
    summary_df = get_operating_summary(period, company_codes=company_codes)
    detail_df = get_multidim_income_statement(period, company_codes=company_codes)
    company_df = _operating_company_metrics(detail_df)
    trend_df = _operating_period_series(periods, period, company_codes)
    previous_period = _operating_previous_period(periods, period)
    previous_summary_df = get_operating_summary(previous_period, company_codes=company_codes) if previous_period else pd.DataFrame()
    previous_detail_df = get_multidim_income_statement(previous_period, company_codes=company_codes) if previous_period else pd.DataFrame()
    structure_df = _operating_structure(detail_df)
    alerts = _operating_alerts(summary_df, previous_summary_df)
    return {
        "period": period,
        "previous_period": previous_period,
        "scope_label": scope_label,
        "company_codes": company_codes,
        "summary_df": summary_df,
        "detail_df": detail_df,
        "company_df": company_df,
        "trend_df": trend_df,
        "previous_summary_df": previous_summary_df,
        "previous_detail_df": previous_detail_df,
        "structure_df": structure_df,
        "alerts": alerts,
        "filters": filters,
    }


def render_profit_dashboard():
    ctx = _profit_page_context(
        "profit_dashboard",
        "利润表总览驾驶舱",
        "管理层先看 KPI、趋势、排名和异常，再下钻到原表明细。",
    )
    if not ctx:
        return
    _render_operating_dashboard_design(
        ctx["period"],
        ctx["scope_label"],
        ctx["company_codes"],
        ctx["summary_df"],
        ctx["previous_summary_df"],
        ctx["detail_df"],
        ctx["company_df"],
        ctx["trend_df"],
        ctx["structure_df"],
        ctx["alerts"],
    )


def render_profit_original_table():
    st.markdown('<div class="page-header">经营汇总表</div>', unsafe_allow_html=True)
    source_periods = get_operating_summary_periods()
    periods = source_periods or get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间。请先导入收入成本费用明细表或其他财务期间数据。")
        return
    filters = _render_workspace_filter_bar(
        key_prefix="profit_original",
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="筛选区",
        period_mode="single",
        note="数据来源：收入成本费用明细表。主体范围按公司组织架构展开后汇总。",
    )
    period = filters["period"]
    company_codes = _resolve_filter_company_codes(filters)
    scope_label = _workspace_scope_label(filters)
    previous_period = _operating_previous_period(periods, period)
    source_df = get_operating_summary_source_detail(period, company_codes)
    source_df = apply_internal_management_fee_elimination(source_df, company_codes)
    previous_source_df = (
        get_operating_summary_source_detail(previous_period, company_codes)
        if previous_period
        else pd.DataFrame()
    )
    previous_source_df = apply_internal_management_fee_elimination(previous_source_df, company_codes)
    operating_rows = build_operating_summary_rows(source_df, previous_source_df)
    if not operating_rows:
        st.warning("当前期间暂无收入成本费用明细表数据，已先展示经营汇总表结构。请在数据导入中导入“收入成本费用明细表/损益明细表”后生成真实金额。")
        operating_rows = build_empty_operating_summary_rows()
    _render_operating_original_design(
        period,
        scope_label,
        company_codes,
        pd.DataFrame(),
        pd.DataFrame(),
        filters,
        operating_rows,
    )


def _build_operating_original_rows_for_scope(
    period: str,
    previous_period: str | None,
    company_codes: list[str],
) -> list[dict]:
    source_df = get_operating_summary_source_detail(period, company_codes)
    source_df = apply_internal_management_fee_elimination(source_df, company_codes)
    previous_source_df = (
        get_operating_summary_source_detail(previous_period, company_codes)
        if previous_period
        else pd.DataFrame()
    )
    previous_source_df = apply_internal_management_fee_elimination(previous_source_df, company_codes)
    return build_operating_summary_rows(source_df, previous_source_df)


EXPENSE_FOCUS_CATEGORY_RULES = [
    {
        "category": "人工成本",
        "items": {"工资", "奖金", "社保费", "社保", "公积金", "福利费", "教师福利", "劳务费", "招聘费"},
        "status": lambda cost_ratio, revenue_ratio: "人工成本占比较高，优先复核排班、课酬和社保口径。" if cost_ratio >= 0.6 else "人工成本为最大成本项，保持月度跟踪。",
    },
    {
        "category": "租金水电物业",
        "items": {"房租", "水电费", "物业管理费"},
        "status": lambda cost_ratio, revenue_ratio: "固定大项压力偏高，建议复核校区面积和能耗。" if cost_ratio >= 0.1 else "固定大项压力可控，关注异常校区。",
    },
    {
        "category": "折旧摊销",
        "items": {"折旧费", "待摊费"},
        "status": lambda cost_ratio, revenue_ratio: "折旧摊销压力需关注，避免与合计行重复统计。" if cost_ratio >= 0.06 else "按折旧费和待摊费明细统计，未叠加合计行。",
    },
    {
        "category": "交际接待交通",
        "items": {"招待费", "交际费", "市内交通费", "差旅费", "汽车费"},
        "status": lambda cost_ratio, revenue_ratio: "波动费用偏高，建议查看主要经营单位。" if cost_ratio >= 0.03 else "波动费用未见明显失控。",
    },
    {
        "category": "办公行政",
        "items": {"办公费", "通信费", "网络服务费", "维修费", "培训费", "保险费", "中介服务费"},
        "status": lambda cost_ratio, revenue_ratio: "办公行政费用偏高，建议拆看维修、培训和中介服务。" if cost_ratio >= 0.03 else "办公行政支出整体可控。",
    },
    {
        "category": "财务费用",
        "items": {"手续费", "利息收入", "利息支出"},
        "status": lambda cost_ratio, revenue_ratio: "资金成本需关注，建议复核手续费和利息项目。" if cost_ratio >= 0.02 else "财务费用占比较低。",
    },
]
EXPENSE_MANAGEMENT_FEE_ITEMS = {"管理费服务费"}
EXPENSE_DENOMINATOR_ITEMS = {"成本费用合计", "收入合计"}


def _is_income_cost_detail_row(row: dict) -> bool:
    account_code = str(row.get("account_code") or "").strip()
    return not (account_code.startswith("OPERATING_") or account_code.startswith("SUMMARY_"))


def _preferred_expense_denominator(source_df: pd.DataFrame, item_name: str) -> float:
    if source_df is None or source_df.empty:
        return 0.0
    rows = source_df[source_df["source_item_name"].astype(str).str.strip() == item_name].copy()
    if rows.empty:
        return 0.0
    rows["source_priority"] = rows["account_code"].astype(str).map(
        lambda value: 0 if value.startswith("OPERATING_") else 1 if value.startswith("SUMMARY_") else 2
    )
    selected = []
    for _, group in rows.groupby("company_code", dropna=False):
        best = group[group["source_priority"] == group["source_priority"].min()]
        selected.append(best.tail(1))
    if not selected:
        return 0.0
    selected_df = pd.concat(selected, ignore_index=True)
    return _safe_float(pd.to_numeric(selected_df["current_amount"], errors="coerce").fillna(0.0).sum())


def _expense_ratio(amount: float, denominator: float) -> float:
    denominator = _safe_float(denominator)
    if abs(denominator) < 1e-9:
        return 0.0
    return _safe_float(amount) / denominator


def _expense_bridge_summary(cost_total: float, categories: pd.DataFrame, management_amount: float) -> dict:
    six_total = 0.0
    if categories is not None and not categories.empty and "本月金额" in categories.columns:
        six_total = _safe_float(pd.to_numeric(categories["本月金额"], errors="coerce").fillna(0.0).sum())
    raw_difference = _safe_float(cost_total) - six_total - _safe_float(management_amount)
    is_negative = raw_difference < -1e-9
    return {
        "cost_total": _safe_float(cost_total),
        "six_category_total": six_total,
        "management_fee": _safe_float(management_amount),
        "other_fee": 0.0 if is_negative else _safe_float(raw_difference),
        "check_difference": _safe_float(abs(raw_difference)) if is_negative else 0.0,
        "raw_difference": _safe_float(raw_difference),
        "label": "待核对差额" if is_negative else "其他费用",
        "status": "warning" if is_negative else "ok",
    }


def _expense_bridge_sentence(bridge: dict) -> str:
    if not isinstance(bridge, dict) or not bridge:
        return "成本费用合计 = 六类重点费用 + 管理费服务费 + 其他费用。"
    if bridge.get("status") == "warning":
        return (
            "成本费用合计 = 六类重点费用 + 管理费服务费 - 待核对差额；"
            f"当前差额 {_fmt_money_compact(bridge.get('check_difference'))}，需复核范围或重复归集。"
        )
    return (
        "成本费用合计 = 六类重点费用 + 管理费服务费 + 其他费用；"
        f"其他费用 {_fmt_money_compact(bridge.get('other_fee'))}。"
    )


def build_focus_expense_analysis(source_df: pd.DataFrame) -> dict:
    if source_df is None or source_df.empty:
        empty = pd.DataFrame(columns=["费用类别", "本月金额", "占成本费用比", "占收入比", "状态说明"])
        bridge = _expense_bridge_summary(0.0, empty, 0.0)
        return {
            "categories": empty,
            "ranking": pd.DataFrame(columns=["费用类别", "主要经营单位", "本月金额", "占比", "判断"]),
            "management_fee": {"amount": 0.0, "cost_ratio": 0.0, "revenue_ratio": 0.0},
            "expense_bridge": bridge,
            "cost_total": 0.0,
            "revenue_total": 0.0,
            "conclusion": "当前期间暂无收入成本费用明细表数据。",
        }

    source = source_df.copy()
    for column in ["source_item_name", "company_name", "company_code", "account_code"]:
        if column not in source.columns:
            source[column] = ""
    if "current_amount" not in source.columns:
        source["current_amount"] = 0.0
    source["source_item_name"] = source["source_item_name"].astype(str).str.strip()
    source["current_amount"] = pd.to_numeric(source["current_amount"], errors="coerce").fillna(0.0)
    cost_total = _preferred_expense_denominator(source, "成本费用合计")
    revenue_total = _preferred_expense_denominator(source, "收入合计")
    detail = source[source.apply(lambda row: _is_income_cost_detail_row(row.to_dict()), axis=1)].copy()

    category_rows = []
    ranking_rows = []
    for rule in EXPENSE_FOCUS_CATEGORY_RULES:
        matched = detail[detail["source_item_name"].isin(rule["items"])].copy()
        amount = _safe_float(matched["current_amount"].sum()) if len(matched) else 0.0
        cost_ratio = _expense_ratio(amount, cost_total)
        revenue_ratio = _expense_ratio(amount, revenue_total)
        status = rule["status"](cost_ratio, revenue_ratio)
        category_rows.append(
            {
                "费用类别": rule["category"],
                "本月金额": amount,
                "占成本费用比": cost_ratio,
                "占收入比": revenue_ratio,
                "状态说明": status,
            }
        )
        if len(matched):
            by_company = (
                matched.groupby(["company_code", "company_name"], dropna=False)["current_amount"]
                .sum()
                .reset_index()
                .sort_values("current_amount", ascending=False, kind="mergesort")
            )
            top = by_company.iloc[0].to_dict()
            ranking_rows.append(
                {
                    "费用类别": rule["category"],
                    "主要经营单位": str(top.get("company_name") or top.get("company_code") or "未识别"),
                    "本月金额": _safe_float(top.get("current_amount")),
                    "占比": _expense_ratio(top.get("current_amount"), amount),
                    "判断": status,
                }
            )
        else:
            ranking_rows.append(
                {
                    "费用类别": rule["category"],
                    "主要经营单位": "-",
                    "本月金额": 0.0,
                    "占比": 0.0,
                    "判断": "未匹配到该类费用明细。",
                }
            )

    management_rows = detail[detail["source_item_name"].isin(EXPENSE_MANAGEMENT_FEE_ITEMS)].copy()
    management_amount = _safe_float(management_rows["current_amount"].sum()) if len(management_rows) else 0.0
    categories = pd.DataFrame(category_rows)
    ranking = pd.DataFrame(ranking_rows)
    top_external = categories.sort_values("本月金额", ascending=False, kind="mergesort").head(2)
    top_text = "、".join(
        f"{row['费用类别']}占成本费用{_safe_float(row['占成本费用比']) * 100:.1f}%"
        for row in top_external.to_dict("records")
    )
    management_text = (
        f"管理费服务费{_fmt_money_compact(management_amount)}需按合并口径单独提示"
        if abs(management_amount) > 1e-9
        else "管理费服务费本期未匹配到明细"
    )
    bridge = _expense_bridge_summary(cost_total, categories, management_amount)
    return {
        "categories": categories,
        "ranking": ranking,
        "management_fee": {
            "amount": management_amount,
            "cost_ratio": _expense_ratio(management_amount, cost_total),
            "revenue_ratio": _expense_ratio(management_amount, revenue_total),
        },
        "expense_bridge": bridge,
        "cost_total": cost_total,
        "revenue_total": revenue_total,
        "conclusion": f"本月费用重点：{top_text}，{management_text}。{_expense_bridge_sentence(bridge)}",
    }


def _render_focus_expense_cards(categories: pd.DataFrame) -> None:
    cards: list[str] = []
    for row in categories.to_dict("records"):
        cards.append(
            '<div class="focus-expense-card">'
            f'<div class="focus-expense-title">{_html(row["费用类别"])}</div>'
            f'<div class="focus-expense-value">{_html(_fmt_money_compact(row["本月金额"]))}</div>'
            f'<div class="focus-expense-meta">占成本费用 {_safe_float(row["占成本费用比"]) * 100:.1f}% · 占收入 {_safe_float(row["占收入比"]) * 100:.1f}%</div>'
            f'<div class="focus-expense-note">{_html(row["状态说明"])}</div>'
            "</div>"
        )
    _render_html(
        """
        <style>
          .focus-expense-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:12px 0 18px;}
          .focus-expense-card{background:#fff;border:1px solid #d9e4f2;border-radius:14px;padding:16px;box-shadow:0 8px 20px rgba(15,35,65,.06);}
          .focus-expense-title{font-size:15px;font-weight:800;color:#10233f;margin-bottom:8px;}
          .focus-expense-value{font-size:22px;font-weight:850;color:#1f6feb;margin-bottom:8px;}
          .focus-expense-meta{font-size:13px;color:#5c6f8a;line-height:1.45;}
          .focus-expense-note{font-size:13px;color:#17233b;margin-top:10px;line-height:1.45;}
          @media (max-width: 980px){.focus-expense-grid{grid-template-columns:1fr;}}
        </style>
        """
        f'<div class="focus-expense-grid">{"".join(cards)}</div>'
    )


def render_expense_subject_analysis():
    st.markdown('<div class="page-header">重点费用分析</div>', unsafe_allow_html=True)
    periods = get_operating_summary_periods() or get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间。请先导入收入成本费用明细表。")
        return
    filters = _render_workspace_filter_bar(
        key_prefix="expense_subject",
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="筛选区",
        period_mode="single",
        note="数据来源：收入成本费用表明细。管理费服务费属于内部管理收费，本页单独提示，不与外部费用混看。",
    )
    period = filters["period"]
    company_codes = _resolve_filter_company_codes(filters)
    scope_label = _workspace_scope_label(filters)
    source_df = get_operating_summary_source_detail(period, company_codes)
    analysis = build_focus_expense_analysis(source_df)

    st.info(analysis["conclusion"])
    if source_df.empty:
        st.warning("当前范围暂无收入成本费用明细。")
        return

    st.markdown("### 六类重点费用")
    _render_focus_expense_cards(analysis["categories"])

    st.markdown("### 重点费用单位排行")
    ranking_display = analysis["ranking"].copy()
    if len(ranking_display):
        ranking_display["占比"] = ranking_display["占比"].map(lambda value: _safe_float(value) * 100)
    st.dataframe(
        ranking_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "本月金额": st.column_config.NumberColumn("本月金额", format="%,.2f"),
            "占比": st.column_config.NumberColumn("占比", format="%.1f%%"),
        },
    )

    management = analysis["management_fee"]
    bridge = analysis.get("expense_bridge", {})
    st.markdown("### 口径提醒")
    with st.container(border=True):
        st.markdown(
            f"""
            **管理费服务费** {_fmt_money_compact(management["amount"])}，
            占成本费用 {_safe_float(management["cost_ratio"]) * 100:.1f}%、
            占收入 {_safe_float(management["revenue_ratio"]) * 100:.1f}%。
            该项目属于内部管理收费，合并口径下后续需要抵消，不与外部经营费用混看。

            **{_html(bridge.get("label", "其他费用"))}** {_fmt_money_compact(bridge.get("check_difference") if bridge.get("status") == "warning" else bridge.get("other_fee"))}。
            {_expense_bridge_sentence(bridge)}
            """
        )
        st.caption(f"当前范围：{scope_label} · 期间：{period} · 分母优先使用收入成本费用表中的成本费用合计和收入合计。")


def render_multi_operating_summary():
    st.markdown('<div class="page-header">经营汇总表</div>', unsafe_allow_html=True)
    periods = get_dashboard_periods()
    if not periods:
        st.info("暂无可展示期间")
        return

    filters = _render_workspace_filter_bar(
        key_prefix="operating_summary",
        periods=periods,
        summary_mode_options=["默认公司", "集团汇总", "板块汇总"],
        group_options=_get_business_group_options(),
        title="经营汇总筛选",
        period_mode="single",
        note="首版按驾驶舱加原表下钻组织：上方看关键指标，中间看主体排名，底部保留原 Excel 宽表和模板预览。",
    )
    period = filters["period"]
    company_codes = _resolve_filter_company_codes(filters)
    scope_label = _workspace_scope_label(filters)

    summary_df = get_operating_summary(period, company_codes=company_codes)
    detail_df = get_multidim_income_statement(period, company_codes=company_codes)
    company_df = _operating_company_metrics(detail_df)
    trend_df = _operating_period_series(periods, period, company_codes)
    previous_period = _operating_previous_period(periods, period)
    previous_summary_df = (
        get_operating_summary(previous_period, company_codes=company_codes)
        if previous_period
        else pd.DataFrame()
    )
    previous_detail_df = (
        get_multidim_income_statement(previous_period, company_codes=company_codes)
        if previous_period
        else pd.DataFrame()
    )
    structure_df = _operating_structure(detail_df)
    alerts = _operating_alerts(summary_df, previous_summary_df)

    revenue = _operating_metric(summary_df, "营业收入")
    cost = _operating_metric(summary_df, "营业成本")
    gross_profit = _operating_metric(summary_df, "毛利")
    expense_total = _operating_metric(summary_df, "费用合计")
    net_profit = _operating_metric(summary_df, "净利润")
    net_margin = _safe_ratio_ui(net_profit, revenue)

    tab_original, tab_dashboard, tab_expense, tab_template = st.tabs(["原表增强", "驾驶舱下钻", "费用科目分析", "模板预览"])
    with tab_original:
        operating_rows = _build_operating_original_rows_for_scope(period, previous_period, company_codes)
        if not operating_rows:
            operating_rows = build_empty_operating_summary_rows()
        _render_operating_original_design(
            period,
            scope_label,
            company_codes,
            detail_df,
            previous_detail_df,
            filters,
            operating_rows,
        )
        if len(summary_df) or len(company_df):
            export_sheets = {"原表增强": _operating_detail_display(detail_df), "经营汇总": summary_df, "主体拆分": company_df}
            st.download_button(
                "导出原表增强数据",
                _dataframes_to_excel_bytes(export_sheets),
                file_name=f"损益汇总表_原表增强_{period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                use_container_width=True,
            )

    with tab_dashboard:
        _render_operating_dashboard_design(
            period,
            scope_label,
            company_codes,
            summary_df,
            previous_summary_df,
            detail_df,
            company_df,
            trend_df,
            structure_df,
            alerts,
        )
        if len(summary_df) or len(company_df):
            export_sheets = {"经营汇总": summary_df, "主体拆分": company_df}
            st.download_button(
                "导出经营汇总",
                _dataframes_to_excel_bytes(export_sheets),
                file_name=f"经营汇总表_{period}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                use_container_width=True,
            )

    with tab_expense:
        st.caption("按 Excel 设计里的方案 B，先把横向宽表拆成费用结构、主体卡片和可下钻明细。")
        _render_bi_kpi_grid(
            [
                {"label": "收入合计", "value": revenue, "type": "money"},
                {"label": "成本费用合计", "value": cost + expense_total, "type": "money"},
                {"label": "净利润", "value": net_profit, "type": "money"},
                {"label": "净利率", "value": net_margin, "type": "percent"},
            ]
        )
        col_expense, col_company = st.columns([1.2, 1], gap="large")
        with col_expense:
            st.markdown('<div class="home-filter-title">费用科目结构</div>', unsafe_allow_html=True)
            if len(structure_df) == 0:
                st.info("暂无费用结构数据。")
            else:
                display = structure_df.copy()
                display["占费用比"] = display["金额"].apply(lambda value: _safe_float(_safe_ratio_ui(value, display["金额"].sum())) * 100)
                st.dataframe(
                    display,
                    use_container_width=True,
                    hide_index=True,
                    height=360,
                    column_config={
                        "金额": st.column_config.NumberColumn("金额", format="%,.2f"),
                        "占费用比": st.column_config.NumberColumn("占费用比", format="%.1f%%"),
                    },
                )
        with col_company:
            st.markdown('<div class="home-filter-title">主体卡片明细</div>', unsafe_allow_html=True)
            _render_operating_company_table(company_df)

    with tab_template:
        st.caption("用于核对原始模板版式。后续明细表会继续向这个宽表样式靠拢。")
        _render_fixed_template_sheet("经营汇总表", "multi_operating_template")


IMPORT_UPLOADER_TOKEN_KEY = "import_uploader_token"
IMPORT_LAST_REPORT_KEY = "import_last_report"


def _get_import_uploader_key(state=None) -> str:
    state = st.session_state if state is None else state
    token = int(state.get(IMPORT_UPLOADER_TOKEN_KEY, 0) or 0)
    if IMPORT_UPLOADER_TOKEN_KEY not in state:
        state[IMPORT_UPLOADER_TOKEN_KEY] = token
    return f"import_wizard_files_{token}"


def _store_import_result_and_reset_uploader(
    report_rows: list[dict],
    success_count: int,
    fail_count: int,
    state=None,
) -> None:
    state = st.session_state if state is None else state
    token = int(state.get(IMPORT_UPLOADER_TOKEN_KEY, 0) or 0)
    state[IMPORT_UPLOADER_TOKEN_KEY] = token + 1
    state[IMPORT_LAST_REPORT_KEY] = {
        "success_count": success_count,
        "fail_count": fail_count,
        "rows": report_rows,
    }


def _render_last_import_report() -> None:
    report = st.session_state.get(IMPORT_LAST_REPORT_KEY)
    if not report:
        return
    rows = report.get("rows") or []
    success_count = int(report.get("success_count") or 0)
    fail_count = int(report.get("fail_count") or 0)
    st.markdown("##### 上次入库报告")
    st.caption(f"导入完成：成功 {success_count} 个，失败 {fail_count} 个。文件选择框已清空，可直接选择下一批。")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_import_upload_tab():
    _render_html(
        """
        <div class="bi-section-grid">
            <div class="bi-panel"><div class="bi-panel-title">1 选择数据类型</div><div class="bi-panel-subtitle">确定本次采集口径</div></div>
            <div class="bi-panel"><div class="bi-panel-title">2 上传文件</div><div class="bi-panel-subtitle">支持批量 Excel</div></div>
            <div class="bi-panel"><div class="bi-panel-title">3 预检入库</div><div class="bi-panel-subtitle">识别公司、期间和表型</div></div>
        </div>
        """
    )

    st.markdown('<div class="home-filter-title">采集任务</div>', unsafe_allow_html=True)
    _render_last_import_report()
    task_col1, task_col2, task_col3, task_col4 = st.columns([1.4, 1.2, 1.2, 1])
    with task_col1:
        manual_type = st.selectbox("数据类型", [""] + REPORT_TYPES_CN, format_func=lambda x: "自动识别" if x == "" else x)
    with task_col2:
        manual_company = st.text_input("经营单元编码", placeholder="自动识别")
    with task_col3:
        manual_period = st.text_input("统计期间", placeholder="YYYYMM / 自动识别")
    with task_col4:
        dup_strategy = st.selectbox("重复策略", ["拒绝", "覆盖"], index=0)
        if dup_strategy == "拒绝":
            st.caption("已存在的数据会拦截；重导请选覆盖。")
    upload_col, action_col = st.columns([2.6, 1.2])
    with upload_col:
        uploaded_files = st.file_uploader(
            "上传 Excel 文件",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key=_get_import_uploader_key(),
        )
    with action_col:
        file_count = len(uploaded_files or [])
        st.markdown(
            f"""
            <div class="bi-panel">
                <div class="bi-panel-title">待处理文件</div>
                <div class="bi-kpi-value">{file_count}</div>
                <div class="bi-panel-subtitle">预检通过后再执行入库</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if uploaded_files:
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
        with btn_col1:
            precheck = st.button("预检", type="secondary", use_container_width=True)
        with btn_col2:
            do_import = st.button("开始入库", type="primary", use_container_width=True)
        with btn_col3:
            st.caption("建议先预检。覆盖策略会替换同公司、同期间、同类型的既有导入。")
        if precheck:
            st.markdown("##### 预检结果")
            for uploaded_file in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name
                try:
                    pc = precheck_import(tmp_path, manual_company or None, manual_period or None, manual_type or None, uploaded_file.name)
                    if pc["passed"]:
                        st.success(f"{uploaded_file.name}: 预检通过")
                        preview_df = pd.DataFrame(
                            [
                                {
                                    "文件名": uploaded_file.name,
                                    "报表类型": pc.get("report_type"),
                                    "经营单元": f"{pc.get('company_name')} ({pc.get('company_code')})",
                                    "期间": pc.get("period"),
                                    "行数": pc.get("row_count"),
                                }
                            ]
                        )
                        st.dataframe(preview_df, use_container_width=True, hide_index=True)
                    else:
                        st.error(f"{uploaded_file.name}: 预检未通过")
                        for e in pc.get("errors", []):
                            st.error(f"  - {e}")
                    for w in pc.get("warnings", []):
                        st.warning(w)
                finally:
                    os.unlink(tmp_path)

        if do_import:
            success_count, fail_count, results = 0, 0, []
            progress_bar = st.progress(0)
            status_text = st.empty()
            for i, uploaded_file in enumerate(uploaded_files):
                status_text.info(f"正在处理: {uploaded_file.name}  ({i+1}/{len(uploaded_files)})")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name
                try:
                    result = import_excel_to_db(tmp_path, manual_company or None, manual_period or None, manual_type or None, uploaded_file.name, duplicate_strategy=dup_strategy)
                    result["file_name"] = uploaded_file.name
                    results.append(result)
                    if result.get("success"): success_count += 1
                    else: fail_count += 1
                except Exception as e:
                    fail_count += 1
                    results.append({"success": False, "file_name": uploaded_file.name, "report_type": "未知", "error": str(e)})
                finally:
                    os.unlink(tmp_path)
                progress_bar.progress((i + 1) / len(uploaded_files))
            status_text.empty()
            progress_bar.empty()
            st.toast(f"导入完成: 成功 {success_count} 个, 失败 {fail_count} 个")
            if success_count > 0:
                st.session_state.companies = get_companies()

            report_rows = []
            for r in results:
                step_errors = []
                for step in r.get("steps", []):
                    info = step.get("info", {}) if isinstance(step, dict) else {}
                    if isinstance(info, dict):
                        step_errors.extend(str(e) for e in info.get("errors", [])[:3])
                    step_errors.extend(str(e) for e in step.get("errors", [])[:3] if isinstance(step, dict))
                if r.get("success"):
                    report_rows.append(
                        {
                            "状态": "成功",
                            "文件名": r.get("file_name", ""),
                            "报表类型": r.get("report_type", ""),
                            "公司": r.get("company_code", ""),
                            "期间": r.get("period", ""),
                            "批次号": r.get("batch_no", ""),
                            "说明": "",
                        }
                    )
                else:
                    err = r.get("error", "导入失败")
                    detail = "；".join(str(e) for e in r.get("validation_errors", [])[:5])
                    if not detail and step_errors:
                        detail = "；".join(step_errors[:5])
                    status_label = "已存在" if str(err).startswith("重复导入") else "失败"
                    if status_label == "已存在":
                        detail = "当前未重复写入；如需重导请选择“覆盖”。"
                    report_rows.append(
                        {
                            "状态": status_label,
                            "文件名": r.get("file_name", ""),
                            "报表类型": r.get("report_type", "未知"),
                            "公司": r.get("company_code", ""),
                            "期间": r.get("period", ""),
                            "批次号": r.get("batch_no", ""),
                            "说明": f"{err} {detail}".strip(),
                        }
                    )
            _store_import_result_and_reset_uploader(report_rows, success_count, fail_count)
            st.rerun()
    else:
        st.info("请先上传需要采集的 Excel 文件。")

    st.markdown("### 导入历史记录")
    try:
        logs = execute_sql("""SELECT batch_no, company_code, period, report_type, status, total_rows, error_rows, file_name, created_at FROM import_logs ORDER BY created_at DESC LIMIT 50""")
        if len(logs) > 0:
            display_cols = {"batch_no": "批次号", "company_code": "公司", "period": "期间", "report_type": "报表类型", "status": "状态", "total_rows": "总行数", "file_name": "文件名", "created_at": "导入时间"}
            logs_display = logs.rename(columns=display_cols)
            logs_display.insert(0, "选择", False)
            edited = st.data_editor(logs_display[["选择"] + list(display_cols.values())], use_container_width=True, hide_index=True, column_config={
                "选择": st.column_config.CheckboxColumn("删除?", help="勾选要删除的记录", default=False),
                "文件名": st.column_config.TextColumn("文件名", width="medium"),
            }, disabled=[c for c in display_cols.values()], key="import_log_editor")

            if edited is not None and edited["选择"].any():
                selected_count = edited["选择"].sum()
                st.markdown(f'<div style="padding:0.5rem 0;color:#1a237e;font-weight:600;">已勾选 <strong>{int(selected_count)}</strong> 条记录</div>', unsafe_allow_html=True)
                col_confirm, col_btn = st.columns([1, 3])
                with col_confirm:
                    confirm = st.checkbox("⚠️ 确认删除所选记录", key="confirm_batch_del")
                with col_btn:
                    if confirm:
                        if st.button(f"🗑️ 删除已选的 {int(selected_count)} 条", type="primary", use_container_width=True):
                            selected = edited[edited["选择"] == True]["批次号"].tolist()
                            session = get_session()
                            try:
                                for batch in selected:
                                    log_info = session.execute(text("SELECT report_type, company_code, period FROM import_logs WHERE batch_no = :b"), {"b": batch}).fetchone()
                                    if log_info:
                                        tbl = log_info[0]
                                        session.execute(text(f"DELETE FROM {tbl} WHERE import_batch = :b"), {"b": batch})
                                    session.execute(text("DELETE FROM import_logs WHERE batch_no = :b"), {"b": batch})
                                session.commit()
                                st.success(f"已成功删除 {len(selected)} 条记录和相关数据")
                            except Exception as ex:
                                session.rollback()
                                st.error(f"删除失败: {ex}")
                            finally:
                                session.close()
                            st.rerun()
        else:
            st.info("暂无导入记录")
    except Exception:
        st.info("暂无导入记录")


def _default_collection_period() -> str:
    periods = get_dashboard_periods()
    if periods:
        return str(periods[0])
    return pd.Timestamp.today().strftime("%Y%m")


def _render_monthly_collection_tab():
    ensure_monthly_collection_schema()
    default_types = [item for item in ["科目余额表", "资产负债表", "损益表"] if item in REPORT_TYPES_CN]
    if not default_types:
        default_types = REPORT_TYPES_CN[:3]

    st.markdown('<div class="home-filter-title">月度收集总览</div>', unsafe_allow_html=True)
    filter_col1, filter_col2 = st.columns([1, 3])
    with filter_col1:
        period = st.text_input("统计期间", value=_default_collection_period(), key="monthly_collection_period")
    with filter_col2:
        selected_types = st.multiselect(
            "应收报表类型",
            REPORT_TYPES_CN,
            default=default_types,
            key="monthly_collection_report_types",
        )

    action_col1, action_col2, action_col3 = st.columns([1, 1, 3])
    with action_col1:
        seed_clicked = st.button("生成本月应收清单", type="primary", use_container_width=True)
    with action_col2:
        refresh_clicked = st.button("刷新收集状态", use_container_width=True)
    with action_col3:
        st.caption("状态根据导入日志重算：缺失、已收集、重复、异常。")

    clean_period = str(period).strip()
    if seed_clicked:
        if not clean_period or not selected_types:
            st.warning("请先填写期间并选择至少一种报表类型。")
        else:
            created = seed_requirements_from_active_companies(clean_period, selected_types)
            refreshed = refresh_collection_status(clean_period)
            st.toast(f"已生成 {created} 条应收清单，刷新 {refreshed} 条状态。")

    if refresh_clicked:
        if not clean_period:
            st.warning("请先填写期间。")
        else:
            refreshed = refresh_collection_status(clean_period)
            st.toast(f"已刷新 {refreshed} 条收集状态。")

    matrix_df = get_collection_matrix(clean_period)
    missing_df = get_collection_missing(clean_period)

    if len(matrix_df) == 0:
        st.info("当前期间还没有应收清单。请先选择报表类型并点击“生成本月应收清单”。")
        return

    status_cols = [col for col in matrix_df.columns if col not in {"公司编码", "公司名称"}]
    flattened = matrix_df[status_cols].stack() if status_cols else pd.Series(dtype="object")
    total_required = int(flattened.shape[0])
    collected_count = int((flattened == "已收集").sum())
    missing_count = int((flattened == "缺失").sum())
    duplicate_count = int((flattened == "重复").sum())
    error_count = int((flattened == "异常").sum())
    completion_rate = (collected_count / total_required) if total_required else 0

    _render_bi_kpi_grid(
        [
            {"label": "应收项", "value": total_required, "type": "number", "delta": None},
            {"label": "已收集", "value": collected_count, "type": "number", "delta": completion_rate},
            {"label": "缺失", "value": missing_count, "type": "number", "delta": None},
            {"label": "异常/重复", "value": error_count + duplicate_count, "type": "number", "delta": None},
        ]
    )

    tab_matrix, tab_issues = st.tabs(["状态矩阵", "缺失/重复/异常明细"])
    with tab_matrix:
        st.dataframe(matrix_df, use_container_width=True, hide_index=True, height=520)
    with tab_issues:
        if len(missing_df) == 0:
            st.success("当前期间没有缺失、重复或异常项。")
        else:
            st.dataframe(
                missing_df,
                use_container_width=True,
                hide_index=True,
                height=420,
                column_config={
                    "成功批次数": st.column_config.NumberColumn("成功批次数", format="%d"),
                    "失败批次数": st.column_config.NumberColumn("失败批次数", format="%d"),
                },
            )


def render_import():
    st.markdown('<div class="page-header">数据采集助手</div>', unsafe_allow_html=True)
    tab_upload, tab_status = st.tabs(["文件采集入库", "月度收集总览"])
    with tab_upload:
        _render_import_upload_tab()
    with tab_status:
        _render_monthly_collection_tab()


def render_account_balance():
    st.markdown('<div class="page-header">📋 科目余额表</div>', unsafe_allow_html=True)
    companies = st.session_state.get("companies", pd.DataFrame())
    company_list = companies["code"].tolist() if not companies.empty else []
    periods = []
    try:
        periods_df = execute_sql("SELECT DISTINCT period FROM account_balance WHERE period IS NOT NULL ORDER BY period DESC")
        periods = periods_df["period"].astype(str).tolist() if len(periods_df) > 0 else []
    except Exception:
        pass
    # 获取科目编码列表
    account_codes = []
    try:
        acct_df = execute_sql("SELECT DISTINCT account_code FROM account_balance ORDER BY account_code")
        account_codes = acct_df["account_code"].tolist() if len(acct_df) > 0 else []
    except Exception:
        pass

    # 公司编码→名称映射
    company_dict = companies.set_index("code")["name"].to_dict() if not companies.empty else {}
    company_list_with_name = list(company_dict.keys())  # 值还是code，显示用format_func

    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    with col1:
        sel_companies = st.multiselect(
            "选择公司（可多选）", company_list_with_name,
            format_func=lambda x: f"{x} - {company_dict.get(x, x)}"
        )
    with col2:
        sel_periods = st.multiselect("期间（可多选）", periods, default=periods[:1])
    with col3:
        summary_mode = st.checkbox("按科目汇总", value=False)
    with col4:
        sel_accounts = st.multiselect("科目编码（可多选）", account_codes)
    if st.button("查询", type="primary", icon=":material/search:", use_container_width=True):
        with st.spinner("⏳ 查询中..."):
            df = get_account_balance(
                company_list=sel_companies if sel_companies else None,
                period_list=sel_periods if sel_periods else None,
                account_list=sel_accounts if sel_accounts else None,
                as_summary=summary_mode,
            )
        if len(df) > 0:
            st.toast(f"查询成功！共 {len(df)} 条记录", icon="✅")

            if summary_mode:
                df_display = _cn_cols(df, {
                    "account_code": "科目编码",
                    "account_name": "科目名称",
                    "opening_balance": "期初余额",
                    "debit_amount": "借方发生额",
                    "credit_amount": "贷方发生额",
                    "ending_balance": "期末余额",
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True, height=500, column_config={
                    "期初余额": st.column_config.NumberColumn("期初余额", format="%,.2f"),
                    "借方发生额": st.column_config.NumberColumn("借方发生额", format="%,.2f"),
                    "贷方发生额": st.column_config.NumberColumn("贷方发生额", format="%,.2f"),
                    "期末余额": st.column_config.NumberColumn("期末余额", format="%,.2f"),
                })
                return

            # 辅助核算为空时显示空白，不显示 None
            if "assist_dimensions" in df.columns:
                df["assist_dimensions"] = df["assist_dimensions"].fillna("")

            # 按 Excel 模板样式：每个科目明细后加科目合计行
            rows_list = []
            # 先按 company_code, account_code 排序
            df = df.sort_values(["company_code", "account_code", "assist_dimensions"])
            for (cc, ac), group in df.groupby(["company_code", "account_code"], sort=False):
                ac_name = group["account_name"].iloc[0]
                has_detail = len(group) > 1  # 有多行明细（如辅助核算拆分）才加合计行
                for _, row in group.iterrows():
                    rows_list.append(row.to_dict())
                if has_detail:
                    # 添加科目合计行
                    total_row = {
                        "company_code": cc,
                        "company_name": group["company_name"].iloc[0],
                        "period": "",
                        "account_code": f"{ac}\\{ac_name}科目合计",
                        "account_name": "科目合计",
                        "opening_balance": group["opening_balance"].sum(),
                        "debit_amount": group["debit_amount"].sum(),
                        "credit_amount": group["credit_amount"].sum(),
                        "ending_balance": group["ending_balance"].sum(),
                        "direction": "",
                        "assist_dimensions": "",
                    }
                    rows_list.append(total_row)

            df_display = pd.DataFrame(rows_list)
            col_map = {"account_code": "科目编码", "account_name": "科目名称",
                       "assist_dimensions": "辅助核算",
                       "opening_balance": "期初余额", "debit_amount": "借方发生额",
                       "credit_amount": "贷方发生额", "ending_balance": "期末余额",
                       "direction": "方向"}
            df_display = _cn_cols(df_display, col_map)

            st.dataframe(df_display, use_container_width=True, hide_index=True, height=500, column_config={
                "科目编码": st.column_config.TextColumn("科目编码", width="small"),
                "期初余额": st.column_config.NumberColumn("期初余额", format="%,.2f"),
                "借方发生额": st.column_config.NumberColumn("借方发生额", format="%,.2f"),
                "贷方发生额": st.column_config.NumberColumn("贷方发生额", format="%,.2f"),
                "期末余额": st.column_config.NumberColumn("期末余额", format="%,.2f"),
            })
        else:
            st.toast("未查询到数据，请检查查询条件", icon="⚠️")

def render_balance_sheet():
    st.markdown('<div class="page-header">📄 资产负债表</div>', unsafe_allow_html=True)
    years, months = _get_year_month_options()
    companies = st.session_state.get("companies", pd.DataFrame())
    company_dict = companies.set_index("code")["name"].to_dict() if not companies.empty else {}
    company_list_with_name = list(company_dict.keys())

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        sel_companies = st.multiselect(
            "选择公司（可多选）", company_list_with_name,
            format_func=lambda x: f"{x} - {company_dict.get(x, x)}", key="bs_c"
        )
    with c2:
        sel_years = st.multiselect("年份（可多选）", years, key="bs_y")
    with c3:
        sel_months = st.multiselect("月份（可多选）", months, key="bs_m")
    if st.button("查询报表", type="primary", icon=":material/description:", use_container_width=True):
        if not sel_companies or not sel_years or not sel_months:
            st.toast("请选择公司和期间", icon="⚠️"); return
        sel_periods = [f"{y}{m}" for y in sel_years for m in sel_months]
        with st.spinner("⏳ 查询中..."):
            placeholders = ",".join([f"'{c}'" for c in sel_companies])
            period_ph = ",".join([f"'{p}'" for p in sel_periods])
            df = execute_sql(f"""
                SELECT side, item_name,
                       COALESCE(line_number,'') as line_number,
                       COALESCE(ending_balance,0.0) as ending_balance,
                       COALESCE(opening_balance,0.0) as opening_balance,
                       is_subtotal, sort_order, company_code, period
                FROM balance_sheet
                WHERE company_code IN ({placeholders}) AND period IN ({period_ph})
                ORDER BY company_code, period, sort_order
            """)
        if len(df) > 0:
            st.toast(f"已找到导入的资产负债表数据，共 {len(df)} 条", icon="✅")
            # 文本列填充空字符串
            for col in ["item_name", "line_number"]:
                df[col] = df[col].fillna("")
            df = df.sort_values(["company_code", "period", "sort_order"]).reset_index(drop=True)
            df["row_key"] = df["sort_order"] // 2
            rows_list = []
            for (cc, pp), grp_outer in df.groupby(["company_code", "period"], sort=False):
                grp = grp_outer.sort_values("sort_order")
                for rk, grp2 in grp.groupby("row_key", sort=True):
                    left = grp2[grp2["sort_order"] % 2 == 0]
                    right = grp2[grp2["sort_order"] % 2 == 1]
                    row_dict = {}
                    if len(left) > 0:
                        lr = left.iloc[0]
                        row_dict["资产"] = lr["item_name"]
                        row_dict["行次"] = str(lr["line_number"]) if lr["line_number"] else ""
                        row_dict["期末余额"] = lr["ending_balance"]
                        row_dict["年初余额"] = lr["opening_balance"]
                    else:
                        row_dict["资产"] = ""; row_dict["行次"] = ""
                        row_dict["期末余额"] = 0; row_dict["年初余额"] = 0
                    if len(right) > 0:
                        rr = right.iloc[0]
                        row_dict["负债和所有者权益"] = rr["item_name"]
                        row_dict["行次2"] = str(rr["line_number"]) if rr["line_number"] else ""
                        row_dict["期末余额2"] = rr["ending_balance"]
                        row_dict["年初余额2"] = rr["opening_balance"]
                    else:
                        row_dict["负债和所有者权益"] = ""; row_dict["行次2"] = ""
                        row_dict["期末余额2"] = 0; row_dict["年初余额2"] = 0
                    rows_list.append(row_dict)
            df_display = pd.DataFrame(rows_list)
            st.dataframe(df_display, use_container_width=True, hide_index=True, height=600,
                         column_config={
                             "资产": st.column_config.TextColumn("资产", width="medium"),
                             "行次": st.column_config.TextColumn("行次", width="small"),
                             "期末余额": st.column_config.NumberColumn("期末余额", format="%,.2f"),
                             "年初余额": st.column_config.NumberColumn("年初余额", format="%,.2f"),
                             "负债和所有者权益": st.column_config.TextColumn("负债和所有者权益", width="medium"),
                             "行次2": st.column_config.TextColumn("行次", width="small"),
                             "期末余额2": st.column_config.NumberColumn("期末余额", format="%,.2f"),
                             "年初余额2": st.column_config.NumberColumn("年初余额", format="%,.2f"),
                         })
            with st.spinner("⏳ 生成导出文件..."):
                fpath = export_balance_sheet(
                    df_display,
                    _company_label(sel_companies, company_dict),
                    _period_label(sel_periods),
                )
                excel_bytes = _read_export_bytes(fpath)
            st.download_button(
                "📥 导出 Excel",
                data=excel_bytes,
                file_name=f"资产负债表_{'_'.join(sel_periods)}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_bs_imported",
            )
        else:
            st.info("未找到导入的资产负债表数据")
            with st.spinner("⏳ 尝试从科目余额表生成..."):
                df = get_balance_sheet(sel_companies[0], sel_periods[0], use_template=True)
            if len(df) > 0:
                st.toast("报表生成成功！", icon="✅")
                df = _cn_cols(df, {"项目": "项目", "行次": "行次", "期末余额": "期末余额"}, keep_only=False)
                st.dataframe(df, use_container_width=True, hide_index=True, height=600,
                             column_config={"期末余额": st.column_config.NumberColumn("期末余额", format="%,.2f")})
                with st.spinner("⏳ 生成导出文件..."):
                    fpath = export_balance_sheet(
                        df,
                        _company_label(sel_companies[0], company_dict),
                        sel_periods[0],
                    )
                    excel_bytes = _read_export_bytes(fpath)
                st.download_button(
                    "📥 导出 Excel",
                    data=excel_bytes,
                    file_name=f"资产负债表_{sel_companies[0]}_{sel_periods[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_bs_generated",
                )
            else:
                st.error("无数据：请先导入资产负债表 Excel 或确保科目余额表有数据")

INCOME_STATEMENT_FIXED_ITEMS = [
    "一、营业收入",
    "减：营业成本",
    "毛利",
    "毛利率",
    "销售费用",
    "管理费用",
    "财务费用",
    "税金及附加",
    "加：投资收益（损失以“-”号填列）",
    "二、营业利润（亏损以“-”号填列）",
    "加：营业外收入",
    "减：营业外支出",
    "三、利润总额（亏损总额以“-”号填列）",
    "减：所得税费用",
    "四、净利润（净亏损以“-”号填列）",
    "净利率",
    "五、净利润（不含计提折旧与摊销）",
    "加：折旧费",
    "加：待摊费",
    "折旧与摊销费合计",
]
INCOME_STATEMENT_PERCENT_ITEMS = {"毛利率", "净利率"}
INCOME_STATEMENT_CORE_ITEMS = [
    "一、营业收入",
    "四、净利润（净亏损以“-”号填列）",
    "毛利率",
    "净利率",
]
INCOME_STATEMENT_FIXED_COMPANY_ORDER = [
    "莞城小学部",
    "莞城初中部",
    "莞城高中部",
    "莞城个性化",
    "南城",
    "石龙",
    "万江",
    "西平",
    "厚街",
    "石碣",
    "虎门",
    "石井",
    "东泰",
    "虎翼营",
    "南城宏图",
    "茶山学前",
    "寮步石大",
    "西平三和",
    "南城虎翼",
    "高埗",
    "长安",
    "拔创中心",
    "书馆管理中心",
    "尔遇书馆莞城",
    "尔遇书馆西平",
    "尔遇书馆东城",
    "尔遇书馆金域",
    "尔遇书馆星城",
    "尔遇书馆龙景",
    "尔遇书馆翡丽山",
    "尔遇书馆西城楼",
    "深圳卓越",
    "东莞国际",
    "管理中心",
    "素质管理中心",
    "探幽文旅",
    "尔遇书城",
    "多维学校",
    "茶山幼儿园",
    "茶山托育",
    "少年宫",
    "合并",
]
INCOME_STATEMENT_COMPANY_DISPLAY_ALIASES = {
    "广东多维教育科技集团有限公司": "管理中心",
}

BUDGET_VERSION = "2026年集团预算"
BUDGET_WORKBOOK_PATH = Path(
    os.environ.get(
        "FINANCE_DW_BUDGET_WORKBOOK",
        str(Path(__file__).resolve().parent / "data" / "2026年集团预算.xlsx"),
    )
)
BUDGET_SHEET_NAME = "2025年总预算（各部门提交）"
BUDGET_QUALITY_CENTER_SHEET_NAME = "2026年素质中心目标校区四季度营收(含个性化)"
BUDGET_MODULE_ORDER = [
    "东莞素质中心",
    "管理中心",
    "尔遇书馆",
    "青少年宫",
    "多维学校",
    "新阳光幼儿园",
    "托育项目",
    "尔遇书城",
    "合计",
]
BUDGET_EXCLUDED_PROJECTS = {"素质中心+管理中心", "尔遇书馆+书馆管理中心"}
BUDGET_MODULE_COMPANY_LABELS = {
    "东莞素质中心": {
        "莞城小学部", "莞城初中部", "莞城高中部", "莞城个性化", "南城", "石龙", "万江",
        "西平", "厚街", "石碣", "虎门", "石井", "东泰", "虎翼营", "南城宏图", "茶山学前",
        "寮步石大", "西平三和", "南城虎翼", "高埗", "长安", "拔创中心",
    },
    "管理中心": {"管理中心", "素质管理中心", "广东多维教育科技集团有限公司", "东莞非学科管理中心"},
    "尔遇书馆": {
        "书馆管理中心", "尔遇书馆莞城", "尔遇书馆西平", "尔遇书馆东城", "尔遇书馆金域",
        "尔遇书馆星城", "尔遇书馆龙景", "尔遇书馆翡丽山", "尔遇书馆西城楼", "深圳卓越",
    },
    "青少年宫": {"少年宫", "青少年宫", "莞城青少年宫"},
    "多维学校": {"多维学校", "东莞市望牛墩多维学校"},
    "新阳光幼儿园": {"新阳光幼儿园", "茶山幼儿园", "幼儿园"},
    "托育项目": {"托育项目", "茶山托育", "茶山托育项目"},
    "尔遇书城": {"尔遇书城"},
    "合计": {"合计", "合并"},
}
BUDGET_BUSINESS_GROUP_MODULES = {
    "非学科素质中心模块": "东莞素质中心",
    "职能公司模块": "管理中心",
    "尔遇书馆模块": "尔遇书馆",
    "少年宫模块": "青少年宫",
    "学校模块": "多维学校",
    "幼儿园模块": "新阳光幼儿园",
}


def get_income_statement_fixed_item_order() -> list[str]:
    return list(INCOME_STATEMENT_FIXED_ITEMS)


def get_income_statement_fixed_company_order() -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in INCOME_STATEMENT_FIXED_COMPANY_ORDER:
        label = str(name or "").strip()
        if label and label not in seen:
            ordered.append(label)
            seen.add(label)
    return ordered


def _income_statement_periods(year: str, months: list[str]) -> list[str]:
    return [f"{year}{month}" for month in months]


def _load_income_statement_rows(periods: list[str], use_cumulative: bool) -> pd.DataFrame:
    if not periods:
        return pd.DataFrame()
    query_periods = [max(periods)] if use_cumulative else periods
    value_col = "cumulative_value" if use_cumulative else "period1_value"
    params = {f"period_{idx}": period for idx, period in enumerate(query_periods)}
    placeholders = ", ".join(f":period_{idx}" for idx in range(len(query_periods)))
    return execute_sql(
        f"""
        SELECT
            ab.company_code,
            COALESCE(NULLIF(TRIM(ab.original_name), ''), '') AS original_name,
            COALESCE(NULLIF(TRIM(c.short_name), ''), '') AS short_name,
            COALESCE(NULLIF(TRIM(c.name), ''), '') AS company_name,
            COALESCE(NULLIF(TRIM(c.tree_path), ''), '') AS tree_path,
            ab.item_name,
            ab.sort_order,
            ab.{value_col} AS statement_value
        FROM income_statement ab
        LEFT JOIN companies c ON ab.company_code = c.code
        WHERE ab.period IN ({placeholders})
        ORDER BY COALESCE(c.tree_path, ''), ab.company_code, ab.sort_order
        """,
        params,
    )


def _income_statement_company_label(row: dict) -> str:
    for key in ("original_name", "short_name", "company_name", "company_code"):
        value = str(row.get(key) or "").strip()
        if value:
            return INCOME_STATEMENT_COMPANY_DISPLAY_ALIASES.get(value, value)
    return "未命名公司"


def _income_statement_company_candidates(row: dict) -> set[str]:
    candidates: set[str] = set()
    for key in ("original_name", "short_name", "company_name", "company_code"):
        value = str(row.get(key) or "").strip()
        if value:
            candidates.add(value)
            candidates.add(INCOME_STATEMENT_COMPANY_DISPLAY_ALIASES.get(value, value))
    return candidates


def _income_statement_company_label_map(df: pd.DataFrame) -> dict[str, str]:
    if df is None or df.empty:
        return {}
    records = []
    for row in df.to_dict("records"):
        records.append(
            {
                "company_code": str(row.get("company_code") or "").strip(),
                "tree_path": str(row.get("tree_path") or "").strip(),
                "label": _income_statement_company_label(row),
                "candidates": _income_statement_company_candidates(row),
            }
        )
    company_df = pd.DataFrame(records).drop_duplicates("company_code")
    if company_df.empty:
        return {}
    company_df = company_df.sort_values(
        by=["tree_path", "company_code"],
        key=lambda series: series.astype(str),
        kind="mergesort",
    )
    label_by_code: dict[str, str] = {}
    used: set[str] = set()
    for row in company_df.to_dict("records"):
        company_code = str(row.get("company_code") or "").strip()
        base_label = str(row.get("label") or company_code or "未命名公司").strip()
        label = base_label
        if label in used:
            suffix = company_code or str(len(used) + 1)
            label = f"{base_label}（{suffix}）"
            counter = 2
            while label in used:
                label = f"{base_label}（{suffix}-{counter}）"
                counter += 1
        label_by_code[company_code] = label
        used.add(label)
    return label_by_code


def _income_statement_company_order_from_label_map(
    df: pd.DataFrame,
    label_by_code: dict[str, str],
) -> list[str]:
    if not label_by_code:
        return []
    records = []
    for row in df.to_dict("records"):
        company_code = str(row.get("company_code") or "").strip()
        if company_code in label_by_code:
            records.append(
                {
                    "company_code": company_code,
                    "tree_path": str(row.get("tree_path") or "").strip(),
                    "label": label_by_code[company_code],
                    "candidates": _income_statement_company_candidates(row),
                }
            )
    company_df = pd.DataFrame(records).drop_duplicates("company_code")
    if company_df.empty:
        return list(label_by_code.values())
    company_df = company_df.sort_values(
        by=["tree_path", "company_code"],
        key=lambda series: series.astype(str),
        kind="mergesort",
    )
    fixed_names = get_income_statement_fixed_company_order()
    labels: list[str] = []
    used_codes: set[str] = set()
    for fixed_name in fixed_names:
        matches = company_df[
            company_df.apply(
                lambda row: fixed_name == row["label"] or fixed_name in row["candidates"],
                axis=1,
            )
        ]
        for row in matches.to_dict("records"):
            company_code = str(row.get("company_code") or "").strip()
            if company_code not in used_codes:
                labels.append(str(row.get("label") or "").strip())
                used_codes.add(company_code)
    for row in company_df.to_dict("records"):
        company_code = str(row.get("company_code") or "").strip()
        if company_code not in used_codes:
            labels.append(str(row.get("label") or "").strip())
            used_codes.add(company_code)
    return [label for label in labels if label]


def get_income_statement_company_order(df: pd.DataFrame) -> list[str]:
    label_by_code = _income_statement_company_label_map(df)
    return _income_statement_company_order_from_label_map(df, label_by_code)


def _income_statement_item_order(df: pd.DataFrame, available_items: set[str] | None = None) -> list[str]:
    if df is None or df.empty:
        return get_income_statement_fixed_item_order()
    fixed = get_income_statement_fixed_item_order()
    fixed_set = set(fixed)
    present = available_items if available_items is not None else set(df["item_name"].dropna().astype(str))
    ordered = [item for item in fixed if item in present]
    extra_df = (
        df.loc[~df["item_name"].astype(str).isin(fixed_set), ["item_name", "sort_order"]]
        .copy()
        .drop_duplicates("item_name")
    )
    if len(extra_df):
        extra_df["sort_order"] = pd.to_numeric(extra_df["sort_order"], errors="coerce").fillna(999999)
        extra_df = extra_df.sort_values(["sort_order", "item_name"], kind="mergesort")
        ordered.extend(extra_df["item_name"].astype(str).tolist())
    return ordered


def _safe_income_statement_ratio(numerator, denominator) -> float:
    denominator_value = _safe_float(denominator)
    if abs(denominator_value) < 1e-9:
        return 0.0
    return _safe_float(numerator) / denominator_value


def _income_statement_value_missing(value) -> bool:
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_income_statement_statement_values(series: pd.Series) -> pd.Series:
    cleaned = series.map(lambda value: pd.NA if _income_statement_value_missing(value) else value)
    return pd.to_numeric(cleaned, errors="coerce")


def _sum_income_statement_values(series: pd.Series):
    return pd.to_numeric(series, errors="coerce").sum(min_count=1)


def _complete_income_statement_ratio_rows(pivot: pd.DataFrame) -> pd.DataFrame:
    if pivot is None or pivot.empty:
        return pivot
    completed = pivot.copy()
    if "毛利率" not in completed.index and {"一、营业收入", "减：营业成本"}.issubset(completed.index):
        completed.loc["毛利率"] = pd.NA
    if "毛利率" in completed.index and {"一、营业收入", "减：营业成本"}.issubset(completed.index):
        for column in completed.columns:
            if not _income_statement_value_missing(completed.at["毛利率", column]):
                continue
            revenue = completed.at["一、营业收入", column]
            cost = completed.at["减：营业成本", column]
            if _income_statement_value_missing(revenue) or _income_statement_value_missing(cost):
                continue
            completed.at["毛利率", column] = _safe_income_statement_ratio(
                _safe_float(revenue) - _safe_float(cost),
                revenue,
            )
    if "净利率" not in completed.index and {"一、营业收入", "四、净利润（净亏损以“-”号填列）"}.issubset(completed.index):
        completed.loc["净利率"] = pd.NA
    if "净利率" in completed.index and {"一、营业收入", "四、净利润（净亏损以“-”号填列）"}.issubset(completed.index):
        for column in completed.columns:
            if not _income_statement_value_missing(completed.at["净利率", column]):
                continue
            revenue = completed.at["一、营业收入", column]
            net_profit = completed.at["四、净利润（净亏损以“-”号填列）", column]
            if _income_statement_value_missing(revenue) or _income_statement_value_missing(net_profit):
                continue
            completed.at["净利率", column] = _safe_income_statement_ratio(net_profit, revenue)
    return completed


def build_income_statement_pivot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["项目"])
    source = df.copy()
    source["company_code"] = source["company_code"].astype(str).str.strip()
    source["statement_value"] = _normalize_income_statement_statement_values(source["statement_value"])
    label_by_code = _income_statement_company_label_map(source)
    source["company_label"] = source["company_code"].map(label_by_code)
    missing_label = source["company_label"].isna()
    if missing_label.any():
        source.loc[missing_label, "company_label"] = source.loc[missing_label].apply(
            lambda row: _income_statement_company_label(row.to_dict()),
            axis=1,
        )
    company_order = _income_statement_company_order_from_label_map(source, label_by_code)
    pivot = source.pivot_table(
        index="item_name",
        columns="company_label",
        values="statement_value",
        aggfunc=_sum_income_statement_values,
    )
    pivot = _complete_income_statement_ratio_rows(pivot)
    item_order = _income_statement_item_order(source, set(pivot.index.astype(str)))
    pivot = pivot.reindex(item_order).fillna(0.0).reset_index().rename(columns={"item_name": "项目"})
    columns = ["项目"] + [company for company in company_order if company in pivot.columns]
    extra_columns = [column for column in pivot.columns if column not in columns]
    return pivot[columns + extra_columns]


def filter_income_statement_display_rows(pivot: pd.DataFrame, compact_view: bool = False) -> pd.DataFrame:
    if pivot is None or pivot.empty or not compact_view:
        return pivot
    core_items = [item for item in INCOME_STATEMENT_CORE_ITEMS if item in set(pivot["项目"].astype(str))]
    return pivot.loc[pivot["项目"].astype(str).isin(core_items)].set_index("项目").reindex(core_items).reset_index()


def _format_income_statement_value(item_name: str, value: object) -> str:
    number = _safe_float(value)
    if item_name in INCOME_STATEMENT_PERCENT_ITEMS:
        return f"{number * 100:.2f}%"
    return f"{number:,.2f}"


def format_income_statement_display(pivot: pd.DataFrame) -> pd.DataFrame:
    if pivot is None or pivot.empty:
        return pd.DataFrame(columns=["项目"])
    display = pivot.copy().astype(object)
    for idx, row in display.iterrows():
        item_name = str(row.get("项目") or "")
        for column in display.columns:
            if column == "项目":
                continue
            display.at[idx, column] = _format_income_statement_value(item_name, row.get(column))
    return display


def _income_statement_table_html(display_df: pd.DataFrame, value_df: pd.DataFrame | None = None) -> str:
    if display_df is None or display_df.empty:
        return '<div class="income-statement-empty">暂无损益表数据。</div>'
    header_html = "".join(f"<th>{_html(column)}</th>" for column in display_df.columns)
    body = []
    value_records = value_df.to_dict("records") if value_df is not None and not value_df.empty else []
    for row_idx, row in enumerate(display_df.to_dict("records")):
        cells = []
        item_name = str(row.get("项目") or "")
        value_row = value_records[row_idx] if row_idx < len(value_records) else {}
        for idx, column in enumerate(display_df.columns):
            cls = "item-cell" if idx == 0 else "amount-cell"
            if (
                idx > 0
                and item_name in INCOME_STATEMENT_PERCENT_ITEMS
                and _safe_float(value_row.get(column)) < 0
            ):
                cls += " negative-rate-cell"
            cells.append(f'<td class="{cls}">{_html(row.get(column, ""))}</td>')
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <style>
      .income-statement-scroll{{overflow:auto;width:100%;max-height:70vh;}}
      .income-statement-table{{border-collapse:collapse;min-width:1160px;width:max-content;background:white;}}
      .income-statement-table th,.income-statement-table td{{border:1px solid #d9e2ef;padding:9px 10px;font-size:14px;line-height:1.35;}}
      .income-statement-table th{{position:sticky;top:0;z-index:4;background:#eaf2ff;color:#10233f;text-align:center;font-weight:700;white-space:normal;}}
      .income-statement-table th:first-child{{left:0;z-index:7;box-shadow:2px 0 0 rgba(148,163,184,.24);}}
      .income-statement-table .item-cell{{position:sticky;left:0;z-index:3;min-width:320px;max-width:420px;white-space:normal;word-break:break-word;text-align:left;font-weight:600;background:#fff;box-shadow:2px 0 0 rgba(148,163,184,.18);}}
      .income-statement-table tbody tr:nth-child(even) .item-cell{{background:#fbfdff;}}
      .income-statement-table .amount-cell{{min-width:145px;text-align:right;white-space:nowrap;}}
      .income-statement-table .negative-rate-cell{{color:#b42318;background:#fff1f0;font-weight:800;}}
    </style>
    <div class="income-statement-scroll">
      <table class="income-statement-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </div>
    """


def render_income_statement():
    st.markdown('<div class="page-header">📈 损益表</div>', unsafe_allow_html=True)
    years, months = _get_year_month_options()
    companies = st.session_state.get("companies", pd.DataFrame())
    company_dict = companies.set_index("code")["name"].to_dict() if not companies.empty else {}
    company_list_with_name = list(company_dict.keys())

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        sel_year = st.selectbox("选择年份", years if years else ["2026"], key="is_y")
    with c2:
        sel_months = st.multiselect("选择月份（可多选）", months, key="is_m")
    with c3:
        st.markdown("<div style='padding-top:28px;'></div>", unsafe_allow_html=True)
        all_months = st.checkbox("📅 全选（全年累计）", value=False, key="is_all")
    compact_view = st.checkbox(
        "只看核心指标",
        value=st.session_state.get("income_statement_compact_view", False),
        key="income_statement_compact_view",
        help="仅显示营业收入、净利润、毛利率、净利率；导出跟随当前显示内容。",
    )
    # 全选时覆盖月份
    if all_months:
        sel_months = months

    if st.button("查询报表", type="primary", icon=":material/monitoring:", use_container_width=True):
        if not sel_year or not sel_months:
            st.toast("请选择年份和月份", icon="⚠️"); return
        sel_periods = _income_statement_periods(sel_year, sel_months)

        with st.spinner("⏳ 查询中..."):
            df = _load_income_statement_rows(sel_periods, use_cumulative=all_months)
        if len(df) > 0:
            st.toast(f"已找到损益表数据", icon="✅")
            pivot = build_income_statement_pivot(df)
            visible_pivot = filter_income_statement_display_rows(pivot, compact_view)
            display = format_income_statement_display(visible_pivot)
            st.markdown(_income_statement_table_html(display, visible_pivot), unsafe_allow_html=True)

            # 导出 Excel（按模板格式）
            with st.spinner("⏳ 生成导出文件..."):
                fpath = export_income_statement_pivot(display, sel_year)
                excel_bytes = _read_export_bytes(fpath)
            st.download_button(
                "📥 导出 Excel",
                data=excel_bytes,
                file_name=f"损益表_{sel_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_pl"
            )
        else:
            st.error("无数据：请先上传损益表 Excel 文件")


def _budget_empty_plan_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["module", "unit_name", "income_budget", "profit_budget", "budget_level"]
    )


def _budget_empty_actual_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["module", "unit_name", "company_code", "income_actual", "profit_actual"]
    )


def _budget_empty_quality_center_targets_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["campus_name", "income_budget"])


def _budget_empty_quality_center_actual_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["actual_name", "company_code", "actual_income"])


def _budget_text(value) -> str:
    return str(value or "").strip()


_BUDGET_PSEUDO_ROW_NAMES = {"合计", "合并", "总计"}


def _budget_is_pseudo_row_label(value) -> bool:
    label = _budget_text(value)
    if not label:
        return False
    return label in _BUDGET_PSEUDO_ROW_NAMES or label.startswith(("SUMMARY_", "OPERATING_"))


def _budget_filter_pseudo_rows(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    attrs = getattr(df, "attrs", {}).copy()
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask = mask | df[column].apply(_budget_is_pseudo_row_label)
    result = df.loc[~mask].copy()
    result.attrs.update(attrs)
    return result


def _budget_numeric(value) -> float:
    if isinstance(value, str) and not value.strip():
        return 0.0
    return _safe_float(value)


def _budget_missing_file_message() -> str:
    return "未找到预算表，请配置 FINANCE_DW_BUDGET_WORKBOOK，或将预算文件放到 data/2026年集团预算.xlsx。"


def budget_time_progress(month: str | int) -> float:
    try:
        month_value = int(str(month).replace("月", "").strip())
    except (TypeError, ValueError):
        month_value = 1
    month_value = min(max(month_value, 1), 12)
    return month_value / 12


def _budget_module_for_name(name: str, business_group: str | None = None) -> str:
    label = INCOME_STATEMENT_COMPANY_DISPLAY_ALIASES.get(_budget_text(name), _budget_text(name))
    if label in BUDGET_MODULE_ORDER:
        return label
    for module, labels in BUDGET_MODULE_COMPANY_LABELS.items():
        if label in labels:
            return module
    if "尔遇书城" in label:
        return "尔遇书城"
    if "尔遇书馆" in label or "书馆管理中心" in label:
        return "尔遇书馆"
    if "少年宫" in label or "青少年宫" in label:
        return "青少年宫"
    if "幼儿园" in label:
        return "新阳光幼儿园"
    if "托育" in label:
        return "托育项目"
    if "学校" in label:
        return "多维学校"
    if "管理中心" in label or "广东多维" in label:
        return "管理中心"
    group = _budget_text(business_group)
    if group in BUDGET_BUSINESS_GROUP_MODULES:
        return BUDGET_BUSINESS_GROUP_MODULES[group]
    return "未分组"


def _budget_module_for_actual_company(
    company_code: str,
    name: str,
    business_group: str | None = None,
) -> str:
    code = _budget_text(company_code)
    if code == HOME_MANAGEMENT_CENTER_CODE:
        return "管理中心"
    if code and code in set(get_consolidation_company_codes("10101")):
        return "东莞素质中心"
    if code and code in set(get_consolidation_company_codes(HOME_ERYU_CENTER_CODE)):
        return "尔遇书馆"
    if code and code in set(get_consolidation_company_codes("10118")):
        return "青少年宫"
    if code and code in set(get_consolidation_company_codes("10108")):
        return "多维学校"
    label = _budget_text(name)
    if "托育" in label:
        return "托育项目"
    if code and code in set(get_consolidation_company_codes("10107")):
        return "新阳光幼儿园"
    return _budget_module_for_name(label, business_group)


def _budget_pl_detail_ytd_source_rows(period: str, company_codes: list[str] | None = None) -> pd.DataFrame:
    columns = [
        "id", "公司编码", "company_code", "item_code", "item_name", "amount", "ytd_amount",
        "short_name", "company_name", "parent_code", "business_group", "公司",
    ]
    if not period:
        return pd.DataFrame(columns=columns)
    params = {"period": period}
    company_sql = ""
    if company_codes is not None:
        codes = [_budget_text(code) for code in company_codes if _budget_text(code)]
        if not codes:
            return pd.DataFrame(columns=columns)
        company_sql = _company_filter_clause("d", codes, params, "budget_pl_ytd")
    try:
        rows = execute_sql(
            f"""
            SELECT
                d.id,
                d.company_code AS 公司编码,
                d.company_code AS company_code,
                d.item_code,
                d.item_name,
                COALESCE(d.ytd_amount, 0) AS amount,
                COALESCE(d.ytd_amount, 0) AS ytd_amount,
                COALESCE(NULLIF(TRIM(c.short_name), ''), '') AS short_name,
                COALESCE(NULLIF(TRIM(c.name), ''), '') AS company_name,
                COALESCE(NULLIF(TRIM(c.parent_code), ''), '') AS parent_code,
                COALESCE(NULLIF(TRIM(dim.business_group), ''), '') AS business_group,
                COALESCE(NULLIF(TRIM(c.name), ''), d.company_code) AS 公司
            FROM pl_detail d
            LEFT JOIN companies c ON CAST(c.code AS TEXT) = CAST(d.company_code AS TEXT)
            LEFT JOIN dim_company dim ON CAST(dim.company_id AS TEXT) = CAST(d.company_code AS TEXT)
            WHERE d.period = :period
              AND d.item_name IN (:revenue_item, :profit_item, :cost_item, :main_revenue_item, :management_fee_item)
              {company_sql}
            """,
            {
                **params,
                "revenue_item": PL_REVENUE_ITEM,
                "profit_item": PL_NET_PROFIT_ITEM,
                "cost_item": PL_COST_TOTAL_ITEM,
                "main_revenue_item": HOME_MAIN_REVENUE_ITEM,
                "management_fee_item": HOME_MANAGEMENT_FEE_ITEM,
            },
        )
    except Exception:
        return pd.DataFrame(columns=columns)
    if rows is None or rows.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in rows.columns:
            rows[column] = ""
    return rows[columns]


def _budget_actual_company_codes(actual_df: pd.DataFrame) -> list[str]:
    if actual_df is None or actual_df.empty or "company_code" not in actual_df.columns:
        return []
    seen: set[str] = set()
    codes: list[str] = []
    for code in actual_df["company_code"].dropna().astype(str).tolist():
        code = _budget_text(code)
        if code and code not in seen and code != "__budget_only__":
            seen.add(code)
            codes.append(code)
    return codes


def _budget_internal_adjustment_for_scope(module_name: str, codes: list[str], adjustments: dict | None) -> float:
    code_set = set(codes)
    module = _budget_text(module_name)
    has_non_subject_receiver = HOME_NON_SUBJECT_CENTER_CODE in code_set
    has_eryu_receiver = HOME_ERYU_CENTER_CODE in code_set
    if module == "东莞素质中心":
        recognized = _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=has_non_subject_receiver,
            include_management=False,
            include_eryu=False,
        )
        unmatched = (
            sum(_safe_float((adjustments or {}).get("non_subject_unmatched_fee", {}).get(code)) for code in code_set)
            if has_non_subject_receiver
            else 0.0
        )
        return _safe_float(recognized + unmatched)
    if module == "尔遇书馆":
        recognized = _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=False,
            include_management=False,
            include_eryu=has_eryu_receiver,
        )
        unmatched = (
            sum(_safe_float((adjustments or {}).get("unmatched_eryu_fee", {}).get(code)) for code in code_set)
            if has_eryu_receiver
            else 0.0
        )
        return _safe_float(recognized + unmatched)
    if module == "合计":
        recognized = _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=has_non_subject_receiver,
            include_management=HOME_MANAGEMENT_CENTER_CODE in code_set,
            include_eryu=has_eryu_receiver,
        )
        unmatched = 0.0
        if has_non_subject_receiver:
            unmatched += sum(
                _safe_float((adjustments or {}).get("non_subject_unmatched_fee", {}).get(code))
                for code in code_set
            )
        if has_eryu_receiver:
            unmatched += sum(
                _safe_float((adjustments or {}).get("unmatched_eryu_fee", {}).get(code))
                for code in code_set
            )
        return _safe_float(recognized + unmatched)
    return 0.0


def _budget_internal_adjustment_context(actual_df: pd.DataFrame, period: str) -> dict:
    codes = _budget_actual_company_codes(actual_df)
    if not codes:
        return {"period": period, "module_adjustments": {}, "total_adjustment": 0.0, "components": {}}
    code_set = set(codes)
    source_rows = _budget_pl_detail_ytd_source_rows(period, codes)
    metrics = _operating_card_company_metrics_from_source(source_rows)
    adjustments = _operating_card_internal_fee_split(
        source_rows,
        metrics,
        codes,
        assign_residual_to_management=False,
    )
    module_adjustments: dict[str, float] = {}
    if actual_df is not None and not actual_df.empty:
        for module, module_rows in actual_df.groupby(actual_df["module"].astype(str), dropna=False):
            module_codes = _budget_actual_company_codes(module_rows)
            value = _budget_internal_adjustment_for_scope(module, module_codes, adjustments)
            if abs(value) > 1e-9:
                module_adjustments[str(module)] = _safe_float(value)
    total_adjustment = _budget_internal_adjustment_for_scope("合计", codes, adjustments)
    components = {
        "1010101非学科服务费": _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=HOME_NON_SUBJECT_CENTER_CODE in code_set,
            include_management=False,
            include_eryu=False,
        ),
        "1010101非学科待匹配": sum(
            _safe_float((adjustments.get("non_subject_unmatched_fee") or {}).get(code))
            for code in codes
        ) if HOME_NON_SUBJECT_CENTER_CODE in code_set else 0.0,
        "101管理中心服务费": _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=False,
            include_management=HOME_MANAGEMENT_CENTER_CODE in code_set,
            include_eryu=False,
        ),
        "10204尔遇书馆服务费": _operating_card_revenue_cost_adjustment(
            adjustments,
            codes,
            include_non_subject=False,
            include_management=False,
            include_eryu=HOME_ERYU_CENTER_CODE in code_set,
        ),
        "10204尔遇书馆待匹配": sum(
            _safe_float((adjustments.get("unmatched_eryu_fee") or {}).get(code))
            for code in codes
        ) if HOME_ERYU_CENTER_CODE in code_set else 0.0,
    }
    unmatched_total = _safe_float(components["1010101非学科待匹配"] + components["10204尔遇书馆待匹配"])
    return {
        "period": period,
        "company_codes": codes,
        "module_adjustments": module_adjustments,
        "total_adjustment": _safe_float(total_adjustment),
        "components": {key: _safe_float(value) for key, value in components.items()},
        "unmatched_adjustment": unmatched_total,
    }


def _budget_attach_internal_adjustments(actual_df: pd.DataFrame, period: str) -> pd.DataFrame:
    result = actual_df.copy() if actual_df is not None else _budget_empty_actual_frame()
    result.attrs["budget_period"] = period
    result.attrs["budget_internal_adjustments"] = _budget_internal_adjustment_context(result, period)
    return result


def read_budget_plan(
    workbook_path: str | Path = BUDGET_WORKBOOK_PATH,
    sheet_name: str = BUDGET_SHEET_NAME,
) -> pd.DataFrame:
    path = Path(workbook_path)
    if not path.exists():
        return _budget_empty_plan_frame()
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(path, data_only=True, read_only=True)
        if sheet_name not in workbook.sheetnames:
            return _budget_empty_plan_frame()
        sheet = workbook[sheet_name]
        header_row = None
        header_map: dict[str, int] = {}
        required = {"项目", "全年收入", "净利润"}
        for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            values = [_budget_text(value) for value in row]
            if required.issubset(set(values)):
                header_row = row_idx
                header_map = {value: idx for idx, value in enumerate(values) if value}
                break
        if header_row is None:
            return _budget_empty_plan_frame()

        rows = []
        for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
            project = _budget_text(row[header_map["项目"]])
            if not project:
                if rows:
                    break
                continue
            if project in BUDGET_EXCLUDED_PROJECTS or project.endswith("损益"):
                continue
            if project == "项目":
                break
            module = _budget_module_for_name(project)
            level = "module" if project in BUDGET_MODULE_ORDER else "unit"
            rows.append(
                {
                    "module": module,
                    "unit_name": project,
                    "income_budget": _budget_numeric(row[header_map["全年收入"]]),
                    "profit_budget": _budget_numeric(row[header_map["净利润"]]),
                    "budget_level": level,
                }
            )
        if not rows:
            return _budget_empty_plan_frame()
        return pd.DataFrame(rows, columns=_budget_empty_plan_frame().columns)
    except Exception:
        return _budget_empty_plan_frame()


def read_quality_center_campus_budget_targets(
    workbook_path: str | Path = BUDGET_WORKBOOK_PATH,
    sheet_name: str = BUDGET_QUALITY_CENTER_SHEET_NAME,
) -> pd.DataFrame:
    path = Path(workbook_path)
    if not path.exists():
        return _budget_empty_quality_center_targets_frame()
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(path, data_only=True, read_only=True)
        if sheet_name not in workbook.sheetnames:
            return _budget_empty_quality_center_targets_frame()
        sheet = workbook[sheet_name]
        header = [_budget_text(cell.value) for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        target_idx = None
        for idx, value in enumerate(header):
            if value and any(token in value for token in ("合并收入", "全年", "合计", "目标", "总目标")):
                target_idx = idx
                break
        if target_idx is None:
            # The confirmed workbook uses Excel column N for the annual campus target.
            target_idx = 13
        campus_idx = None
        for idx in range(min(target_idx, len(header) - 1), -1, -1):
            if header[idx] == "校区":
                campus_idx = idx
                break
        if campus_idx is None:
            campus_idx = 0

        rows = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if len(row) <= max(campus_idx, target_idx):
                continue
            campus_name = _budget_text(row[campus_idx])
            income_budget = _budget_numeric(row[target_idx])
            if not campus_name or campus_name in {"合计", "总计"} or abs(income_budget) < 1e-9:
                continue
            rows.append({"campus_name": campus_name, "income_budget": income_budget})
        if not rows:
            return _budget_empty_quality_center_targets_frame()
        return pd.DataFrame(rows, columns=_budget_empty_quality_center_targets_frame().columns)
    except Exception:
        return _budget_empty_quality_center_targets_frame()


def load_quality_center_actual_income(period: str) -> pd.DataFrame:
    if not period:
        return _budget_empty_quality_center_actual_frame()
    actuals = load_budget_actuals(period)
    if actuals is None or actuals.empty:
        return _budget_empty_quality_center_actual_frame()
    result = actuals[actuals["module"].astype(str) == "东莞素质中心"].copy()
    if result.empty:
        return _budget_empty_quality_center_actual_frame()
    result = result.rename(columns={"unit_name": "actual_name", "income_actual": "actual_income"})
    result["actual_name"] = result["actual_name"].apply(_budget_text)
    result["company_code"] = result["company_code"].apply(_budget_text)
    result["actual_income"] = pd.to_numeric(result["actual_income"], errors="coerce").fillna(0.0)
    result = result[(result["actual_name"] != "") & (result["company_code"] != "")]
    if result.empty:
        return _budget_empty_quality_center_actual_frame()
    deduped = (
        result.sort_values(["company_code", "actual_name"])
        .groupby("company_code", dropna=False, as_index=False)
        .agg({"actual_name": "first", "actual_income": "sum"})
    )
    return deduped.loc[:, _budget_empty_quality_center_actual_frame().columns]


def _budget_quality_match_key(name: str) -> str:
    text_value = _budget_text(name)
    for token in (
        "东莞市",
        "东莞",
        "多维教育",
        "多维",
        "素质教育",
        "素质",
        "学习中心",
        "中心",
        "校区",
        "分校",
        "总部",
        "部",
    ):
        text_value = text_value.replace(token, "")
    for token in ("（", "）", "(", ")", " ", "　", "&", "＆", "-", "—", "_", "/"):
        text_value = text_value.replace(token, "")
    return text_value.strip()


def _budget_quality_candidate_text(candidates: list[dict]) -> str:
    if not candidates:
        return ""
    values = []
    for candidate in candidates:
        name = _budget_text(candidate.get("actual_name"))
        code = _budget_text(candidate.get("company_code"))
        values.append(f"{name}（{code}）" if code else name)
    return "、".join(values)


def _budget_quality_confirmed_candidate(
    campus_name: str,
    actual_by_name: dict[str, list[dict]],
    actual_by_key: dict[str, list[dict]] | None = None,
) -> dict | None:
    for actual_name in get_budget_campus_name_mappings().get(campus_name, ()):
        candidates = actual_by_name.get(actual_name, [])
        if not candidates and actual_by_key is not None:
            candidates = actual_by_key.get(_budget_quality_match_key(actual_name), [])
        if len(candidates) == 1:
            return candidates[0]
    return None


def match_quality_center_campus_actuals(targets_df: pd.DataFrame, actual_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "campus_name", "income_budget", "actual_name", "company_code", "actual_income",
        "match_status", "match_note",
    ]
    if targets_df is None or targets_df.empty:
        return pd.DataFrame(columns=columns)
    actual_records = [] if actual_df is None or actual_df.empty else actual_df.to_dict("records")
    actual_by_name: dict[str, list[dict]] = {}
    actual_by_key: dict[str, list[dict]] = {}
    for record in actual_records:
        name = _budget_text(record.get("actual_name"))
        if not name:
            continue
        normalized = _budget_quality_match_key(name)
        actual_by_name.setdefault(name, []).append(record)
        if normalized:
            actual_by_key.setdefault(normalized, []).append(record)

    rows = []
    used_company_codes: set[str] = set()
    for target in targets_df.to_dict("records"):
        campus_name = _budget_text(target.get("campus_name"))
        budget = _safe_float(target.get("income_budget"))
        normalized_target = _budget_quality_match_key(campus_name)
        status = "未匹配"
        note = "未找到可靠候选"
        chosen: dict | None = None

        special_statuses = get_budget_campus_special_statuses()
        if campus_name in special_statuses:
            status, note = special_statuses[campus_name]
            rows.append(
                {
                    "campus_name": campus_name,
                    "income_budget": budget,
                    "actual_name": "",
                    "company_code": "",
                    "actual_income": None,
                    "match_status": status,
                    "match_note": note,
                }
            )
            continue

        confirmed_candidate = _budget_quality_confirmed_candidate(campus_name, actual_by_name, actual_by_key)
        if confirmed_candidate:
            code = _budget_text(confirmed_candidate.get("company_code"))
            if code and code in used_company_codes:
                rows.append(
                    {
                        "campus_name": campus_name,
                        "income_budget": budget,
                        "actual_name": "",
                        "company_code": "",
                        "actual_income": None,
                        "match_status": "待确认",
                        "match_note": f"公司编码 {code} 已匹配到其他预算校区，避免重复加总",
                    }
                )
                continue
            if code:
                used_company_codes.add(code)
            rows.append(
                {
                    "campus_name": campus_name,
                    "income_budget": budget,
                    "actual_name": _budget_text(confirmed_candidate.get("actual_name")),
                    "company_code": _budget_text(confirmed_candidate.get("company_code")),
                    "actual_income": _safe_float(confirmed_candidate.get("actual_income")),
                    "match_status": "已匹配",
                    "match_note": f"用户确认映射：{campus_name} -> {_budget_text(confirmed_candidate.get('actual_name'))}",
                }
            )
            continue

        exact_candidates = actual_by_name.get(campus_name, [])
        normalized_candidates = actual_by_key.get(normalized_target, []) if normalized_target else []
        contains_candidates = []
        if normalized_target:
            for record in actual_records:
                actual_key = _budget_quality_match_key(record.get("actual_name"))
                if actual_key and (normalized_target in actual_key or actual_key in normalized_target):
                    contains_candidates.append(record)

        if len(exact_candidates) == 1:
            chosen = exact_candidates[0]
            status = "已匹配"
            note = "名称完全一致"
        elif len(normalized_candidates) == 1:
            chosen = normalized_candidates[0]
            status = "已匹配"
            note = "标准化名称一致"
        elif len(contains_candidates) == 1:
            status = "待确认"
            note = f"候选：{_budget_quality_candidate_text(contains_candidates)}"
        elif len(contains_candidates) > 1:
            status = "待确认"
            note = f"候选不唯一：{_budget_quality_candidate_text(contains_candidates)}"

        if chosen:
            code = _budget_text(chosen.get("company_code"))
            if code and code in used_company_codes:
                note = f"公司编码 {code} 已匹配到其他预算校区，避免重复加总"
                status = "待确认"
                chosen = None
            elif code:
                used_company_codes.add(code)

        rows.append(
            {
                "campus_name": campus_name,
                "income_budget": budget,
                "actual_name": _budget_text(chosen.get("actual_name")) if chosen else "",
                "company_code": _budget_text(chosen.get("company_code")) if chosen else "",
                "actual_income": _safe_float(chosen.get("actual_income")) if chosen else None,
                "match_status": status,
                "match_note": note,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def quality_center_unmatched_items(match_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["预算校区名称", "系统候选名称", "匹配状态", "建议说明"]
    if match_df is None or match_df.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for row in match_df.to_dict("records"):
        status = _budget_text(row.get("match_status"))
        if status in {"已匹配", "待开业", "已取消"}:
            continue
        note = _budget_text(row.get("match_note"))
        candidate = ""
        if "候选：" in note:
            candidate = note.split("候选：", 1)[1]
        elif "候选不唯一：" in note:
            candidate = note.split("候选不唯一：", 1)[1]
        rows.append(
            {
                "预算校区名称": row.get("campus_name"),
                "系统候选名称": candidate or "无",
                "匹配状态": status,
                "建议说明": note,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _budget_actual_unit_label(row: dict) -> str:
    for key in ("original_name", "short_name", "company_name", "company_code"):
        value = _budget_text(row.get(key))
        if value:
            return INCOME_STATEMENT_COMPANY_DISPLAY_ALIASES.get(value, value)
    return "未命名公司"


def _budget_actual_values_match(left: pd.Series, right: pd.Series) -> bool:
    return (
        abs(_safe_float(left.get("income_actual")) - _safe_float(right.get("income_actual"))) < 1e-6
        and abs(_safe_float(left.get("profit_actual")) - _safe_float(right.get("profit_actual"))) < 1e-6
    )


def _budget_prune_stale_parent_actuals(actual: pd.DataFrame) -> pd.DataFrame:
    """Drop stale parent-code duplicates left by old imports; keep single-company rows unchanged."""
    if actual is None or actual.empty or "company_code" not in actual.columns:
        return actual
    rows = actual.reset_index(drop=True).copy()
    drop_indexes: set[int] = set()
    for left_idx, left in rows.iterrows():
        if left_idx in drop_indexes:
            continue
        left_code = _budget_text(left.get("company_code"))
        if not left_code:
            continue
        for right_idx, right in rows.iterrows():
            if left_idx == right_idx or right_idx in drop_indexes:
                continue
            if _budget_text(left.get("module")) != _budget_text(right.get("module")):
                continue
            if not _budget_actual_values_match(left, right):
                continue
            right_code = _budget_text(right.get("company_code"))
            right_parent = _budget_text(right.get("parent_code"))
            if not right_code or left_code == right_code:
                continue
            is_left_parent = right_parent == left_code or (
                len(left_code) < len(right_code) and right_code.startswith(left_code)
            )
            if is_left_parent:
                drop_indexes.add(left_idx)
                break
    if not drop_indexes:
        return actual
    return rows.drop(index=sorted(drop_indexes)).reset_index(drop=True)


def load_budget_actuals(period: str) -> pd.DataFrame:
    if not period:
        return _budget_empty_actual_frame()
    source_rows = _budget_pl_detail_ytd_source_rows(period)
    if source_rows is None or source_rows.empty:
        return _budget_empty_actual_frame()
    target_rows = source_rows[source_rows["item_name"].astype(str).isin({PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM})].copy()
    preferred = preferred_pl_detail_rows(target_rows)
    if preferred.empty:
        return _budget_empty_actual_frame()
    preferred["_amount"] = pd.to_numeric(preferred.get("amount"), errors="coerce").fillna(0.0)
    pivot = (
        preferred.pivot_table(
            index=["company_code", "short_name", "company_name", "parent_code", "business_group"],
            columns="item_name",
            values="_amount",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in (PL_REVENUE_ITEM, PL_NET_PROFIT_ITEM):
        if column not in pivot.columns:
            pivot[column] = 0.0
    rows = []
    for row in pivot.to_dict("records"):
        label = _budget_actual_unit_label(row)
        module = _budget_module_for_actual_company(row.get("company_code"), label, row.get("business_group"))
        rows.append(
            {
                "module": module,
                "unit_name": label,
                "company_code": _budget_text(row.get("company_code")),
                "parent_code": _budget_text(row.get("parent_code")),
                "income_actual": _safe_float(row.get(PL_REVENUE_ITEM)),
                "profit_actual": _safe_float(row.get(PL_NET_PROFIT_ITEM)),
            }
        )
    actual = pd.DataFrame(rows)
    actual = _budget_prune_stale_parent_actuals(actual)
    actual = (
        actual.groupby(["module", "unit_name", "company_code"], dropna=False, as_index=False)
        .agg({"income_actual": "sum", "profit_actual": "sum"})
    )
    return _budget_attach_internal_adjustments(actual[_budget_empty_actual_frame().columns], period)


def _budget_value_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _budget_metric_status(income_gap, profit_gap) -> str:
    gaps = [
        _safe_float(value)
        for value in (income_gap, profit_gap)
        if not _budget_value_missing(value)
    ]
    if not gaps:
        return "暂无预算"
    if all(value >= -1e-9 for value in gaps):
        return "超前" if any(value >= 0.02 for value in gaps) else "正常"
    return "滞后"


def _budget_metric_progress(actual, budget, progress: float, metric: str) -> tuple[float | None, float | None]:
    actual_value = _safe_float(actual)
    budget_value = _safe_float(budget)
    if abs(budget_value) < 1e-9:
        return None, None
    if metric == "profit" and budget_value < 0:
        target = budget_value * progress
        return None, (actual_value - target) / abs(budget_value)
    completion = actual_value / budget_value
    return completion, completion - progress


def build_budget_completion_data(
    plan_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    selected_month: str | int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    progress = budget_time_progress(selected_month)
    plan_df = plan_df.copy() if plan_df is not None else _budget_empty_plan_frame()
    actual_df = actual_df.copy() if actual_df is not None else _budget_empty_actual_frame()
    plan_df = _budget_filter_pseudo_rows(plan_df, ["module", "unit_name"])
    actual_df = _budget_filter_pseudo_rows(actual_df, ["module", "unit_name"])
    internal_context = actual_df.attrs.get("budget_internal_adjustments", {}) if hasattr(actual_df, "attrs") else {}
    module_adjustments = internal_context.get("module_adjustments", {}) if isinstance(internal_context, dict) else {}
    total_adjustment = _safe_float(internal_context.get("total_adjustment")) if isinstance(internal_context, dict) else 0.0

    module_rows = plan_df[plan_df["budget_level"] == "module"] if len(plan_df) else _budget_empty_plan_frame()
    unit_rows = plan_df[plan_df["budget_level"] != "module"] if len(plan_df) else _budget_empty_plan_frame()
    module_budget = (
        module_rows.groupby("module", as_index=False)[["income_budget", "profit_budget"]].sum()
        if len(module_rows)
        else pd.DataFrame(columns=["module", "income_budget", "profit_budget"])
    )
    unit_budget = (
        unit_rows.groupby(["module", "unit_name"], as_index=False)[["income_budget", "profit_budget"]].sum()
        if len(unit_rows)
        else pd.DataFrame(columns=["module", "unit_name", "income_budget", "profit_budget"])
    )
    if len(unit_budget):
        missing_modules = set(unit_budget["module"]) - set(module_budget["module"])
        if missing_modules:
            module_budget = pd.concat(
                [
                    module_budget,
                    unit_budget[unit_budget["module"].isin(missing_modules)]
                    .groupby("module", as_index=False)[["income_budget", "profit_budget"]]
                    .sum(),
                ],
                ignore_index=True,
            )

    actual_by_module = (
        actual_df.groupby("module", as_index=False)[["income_actual", "profit_actual"]].sum()
        if len(actual_df)
        else pd.DataFrame(columns=["module", "income_actual", "profit_actual"])
    )
    modules = [
        module
        for module in BUDGET_MODULE_ORDER
        if module in set(module_budget["module"]).union(set(actual_by_module["module"]))
    ]
    for module in sorted(set(module_budget["module"]).union(set(actual_by_module["module"])) - set(modules)):
        modules.append(module)
    if modules and "合计" not in modules:
        modules.append("合计")

    overview_rows = []
    for module in modules:
        if module == "合计":
            budget_row = module_budget[module_budget["module"] == module]
            if len(budget_row):
                income_budget = _safe_float(budget_row["income_budget"].sum())
                profit_budget = _safe_float(budget_row["profit_budget"].sum())
            else:
                income_budget = _safe_float(module_budget.loc[module_budget["module"] != "合计", "income_budget"].sum())
                profit_budget = _safe_float(module_budget.loc[module_budget["module"] != "合计", "profit_budget"].sum())
            raw_income_actual = _safe_float(actual_by_module.loc[actual_by_module["module"] != "合计", "income_actual"].sum())
            income_actual = raw_income_actual - total_adjustment
            profit_actual = _safe_float(actual_by_module.loc[actual_by_module["module"] != "合计", "profit_actual"].sum())
        else:
            budget_row = module_budget[module_budget["module"] == module]
            actual_row = actual_by_module[actual_by_module["module"] == module]
            income_budget = _safe_float(budget_row["income_budget"].sum()) if len(budget_row) else 0.0
            profit_budget = _safe_float(budget_row["profit_budget"].sum()) if len(budget_row) else 0.0
            raw_income_actual = _safe_float(actual_row["income_actual"].sum()) if len(actual_row) else 0.0
            income_actual = raw_income_actual - _safe_float(module_adjustments.get(module))
            profit_actual = _safe_float(actual_row["profit_actual"].sum()) if len(actual_row) else 0.0
        income_completion, income_gap = _budget_metric_progress(income_actual, income_budget, progress, "income")
        profit_completion, profit_gap = _budget_metric_progress(profit_actual, profit_budget, progress, "profit")
        overview_rows.append(
            {
                "模块名称": module,
                "收入预算": income_budget,
                "收入实际": income_actual,
                "收入完成率": income_completion,
                "时间进度": progress,
                "收入进度差": income_gap,
                "利润预算": profit_budget,
                "利润实际": profit_actual,
                "利润完成率": profit_completion,
                "利润进度差": profit_gap,
                "状态": _budget_metric_status(income_gap, profit_gap),
            }
        )

    details = actual_df.merge(unit_budget, how="left", on=["module", "unit_name"])
    if len(unit_budget):
        missing_actual = unit_budget.merge(actual_df, how="left", on=["module", "unit_name"])
        missing_actual = missing_actual[missing_actual["income_actual"].isna() & missing_actual["profit_actual"].isna()]
        if len(missing_actual):
            details = pd.concat([details, missing_actual], ignore_index=True)
    unit_budget_modules = set(unit_budget["module"].astype(str)) if len(unit_budget) else set()
    if len(module_budget):
        for module_row in module_budget.to_dict("records"):
            module = str(module_row.get("module") or "")
            if not module or module == "合计" or module in unit_budget_modules:
                continue
            income_budget = _safe_float(module_row.get("income_budget"))
            profit_budget = _safe_float(module_row.get("profit_budget"))
            if abs(income_budget) < 1e-9 and abs(profit_budget) < 1e-9:
                continue
            if details.empty:
                module_details = pd.DataFrame()
            else:
                module_details = details[details["module"].astype(str) == module]
            if len(module_details) == 1:
                row_idx = module_details.index[0]
                details.loc[row_idx, "income_budget"] = income_budget
                details.loc[row_idx, "profit_budget"] = profit_budget
            elif len(module_details) == 0:
                details = pd.concat(
                    [
                        details,
                        pd.DataFrame(
                            [
                                {
                                    "module": module,
                                    "unit_name": module,
                                    "company_code": "__budget_only__",
                                    "income_actual": None,
                                    "profit_actual": None,
                                    "income_budget": income_budget,
                                    "profit_budget": profit_budget,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
    if len(details):
        details["income_budget"] = pd.to_numeric(details["income_budget"], errors="coerce").fillna(0.0)
        details["profit_budget"] = pd.to_numeric(details["profit_budget"], errors="coerce").fillna(0.0)
        budget_only_mask = details.get("company_code", pd.Series(dtype=str)).astype(str) == "__budget_only__"
        details.loc[~budget_only_mask, "income_actual"] = pd.to_numeric(
            details.loc[~budget_only_mask, "income_actual"],
            errors="coerce",
        ).fillna(0.0)
        details.loc[~budget_only_mask, "profit_actual"] = pd.to_numeric(
            details.loc[~budget_only_mask, "profit_actual"],
            errors="coerce",
        ).fillna(0.0)
        details.loc[budget_only_mask, ["income_actual", "profit_actual"]] = None
        income_progress = details.apply(
            lambda row: _budget_metric_progress(row["income_actual"], row["income_budget"], progress, "income"),
            axis=1,
        )
        profit_progress = details.apply(
            lambda row: _budget_metric_progress(row["profit_actual"], row["profit_budget"], progress, "profit"),
            axis=1,
        )
        details["收入完成率"] = income_progress.apply(lambda value: value[0])
        details["收入进度差"] = income_progress.apply(lambda value: value[1])
        details["利润完成率"] = profit_progress.apply(lambda value: value[0])
        details["利润进度差"] = profit_progress.apply(lambda value: value[1])
        details["状态"] = details.apply(
            lambda row: _budget_metric_status(row["收入进度差"], row["利润进度差"]),
            axis=1,
        )
        details.loc[budget_only_mask, ["收入完成率", "收入进度差", "利润完成率", "利润进度差"]] = None
        details.loc[budget_only_mask, "状态"] = "待接入"
        details = details.rename(
            columns={
                "unit_name": "公司名称",
                "income_budget": "收入预算",
                "income_actual": "收入实际",
                "profit_budget": "利润预算",
                "profit_actual": "利润实际",
            }
        )
    else:
        details = pd.DataFrame(
            columns=[
                "module", "公司名称", "收入预算", "收入实际", "收入完成率", "收入进度差",
                "利润预算", "利润实际", "利润完成率", "利润进度差", "状态",
            ]
        )
    overview = pd.DataFrame(overview_rows)
    if isinstance(internal_context, dict):
        overview.attrs["budget_internal_adjustments"] = internal_context
        details.attrs["budget_internal_adjustments"] = internal_context
    return overview, details


def _budget_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for column in ["收入完成率", "时间进度", "收入进度差", "利润完成率", "利润进度差"]:
        if column in display.columns:
            display[column] = display[column].apply(
                lambda value: None if _budget_value_missing(value) else _safe_float(value) * 100
            )
    return display


def _render_budget_dataframe(df: pd.DataFrame, height: int = 360) -> None:
    if df is None or df.empty:
        st.info("当前范围暂无预算或实际数据。")
        return
    display = _budget_display_frame(df)
    money_cols = {
        "收入预算",
        "收入实际",
        "利润预算",
        "利润实际",
        "收入预算（万元）",
        "收入实际（万元）",
        "利润预算（万元）",
        "利润实际（万元）",
    }
    percent_cols = {"收入完成率", "时间进度", "收入进度差", "利润完成率", "利润进度差"}
    column_config = {
        column: st.column_config.NumberColumn(column, format="%,.2f")
        for column in display.columns
        if column in money_cols
    }
    column_config.update(
        {
            column: st.column_config.NumberColumn(column, format="%.2f%%")
            for column in display.columns
            if column in percent_cols
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True, height=height, column_config=column_config)


def _format_budget_progress_cell(completion, progress, gap) -> str:
    progress_text = f"时间进度 {_safe_float(progress) * 100:.2f}%"
    if _budget_value_missing(gap):
        return progress_text
    gap_value = _safe_float(gap)
    direction = "高于进度" if gap_value >= 0 else "低于进度"
    gap_text = f"{direction} {abs(gap_value) * 100:.2f}%"
    if _budget_value_missing(completion):
        return f"{progress_text} / 预算偏差 {gap_value * 100:.2f}%"
    return f"完成率 {_safe_float(completion) * 100:.2f}% / {progress_text} / {gap_text}"


def _budget_overview_view(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    view = df.copy()
    view["收入进度"] = view.apply(
        lambda row: _format_budget_progress_cell(row.get("收入完成率"), row.get("时间进度"), row.get("收入进度差")),
        axis=1,
    )
    view["利润进度"] = view.apply(
        lambda row: _format_budget_progress_cell(row.get("利润完成率"), row.get("时间进度"), row.get("利润进度差")),
        axis=1,
    )
    return view[
        [
            "模块名称", "收入预算", "收入实际", "收入进度",
            "利润预算", "利润实际", "利润进度", "状态",
        ]
    ]


def _budget_detail_view(df: pd.DataFrame, progress: float) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    view = _budget_filter_pseudo_rows(df.copy(), ["module", "公司名称", "unit_name"])
    view["收入进度"] = view.apply(
        lambda row: _format_budget_progress_cell(row.get("收入完成率"), progress, row.get("收入进度差")),
        axis=1,
    )
    view["利润进度"] = view.apply(
        lambda row: _format_budget_progress_cell(row.get("利润完成率"), progress, row.get("利润进度差")),
        axis=1,
    )
    return view[
        [
            "公司名称", "收入预算", "收入实际", "收入进度",
            "利润预算", "利润实际", "利润进度", "状态",
        ]
    ]


def _budget_module_drilldown_view(module_name: str, detail_df: pd.DataFrame, progress: float) -> pd.DataFrame:
    if detail_df is None or detail_df.empty:
        return pd.DataFrame()
    drill_df = detail_df[detail_df["module"].astype(str) == str(module_name)].copy()
    if drill_df.empty:
        return pd.DataFrame()
    view = _budget_detail_view(drill_df, progress).reset_index(drop=True).astype(object)
    for output_idx, (_, source_row) in enumerate(drill_df.reset_index(drop=True).iterrows()):
        income_budget = _safe_float(source_row.get("收入预算"))
        profit_budget = _safe_float(source_row.get("利润预算"))
        code = _budget_text(source_row.get("company_code"))
        if abs(income_budget) < 1e-9:
            view.loc[output_idx, "收入预算"] = "暂无预算"
            view.loc[output_idx, "收入进度"] = "暂无预算"
        if abs(profit_budget) < 1e-9:
            view.loc[output_idx, "利润预算"] = "暂无预算"
            view.loc[output_idx, "利润进度"] = "暂无预算"
        if code == "__budget_only__":
            view.loc[output_idx, "收入实际"] = "待接入"
            view.loc[output_idx, "利润实际"] = "待接入"
            view.loc[output_idx, "收入进度"] = "待接入"
            view.loc[output_idx, "利润进度"] = "待接入"
            view.loc[output_idx, "状态"] = "待接入"
    return view


def _budget_total_row(overview_df: pd.DataFrame) -> dict:
    if overview_df is None or overview_df.empty:
        return {}
    total = overview_df[overview_df["模块名称"].astype(str) == "合计"]
    if len(total):
        return total.iloc[0].to_dict()
    numeric_cols = ["收入预算", "收入实际", "利润预算", "利润实际"]
    row = {"模块名称": "合计"}
    for col in numeric_cols:
        row[col] = _safe_float(pd.to_numeric(overview_df[col], errors="coerce").fillna(0.0).sum())
    progress = _safe_float(overview_df["时间进度"].iloc[0]) if "时间进度" in overview_df.columns and len(overview_df) else 0.0
    income_completion, income_gap = _budget_metric_progress(row["收入实际"], row["收入预算"], progress, "income")
    profit_completion, profit_gap = _budget_metric_progress(row["利润实际"], row["利润预算"], progress, "profit")
    row.update(
        {
            "收入完成率": income_completion,
            "利润完成率": profit_completion,
            "时间进度": progress,
            "收入进度差": income_gap,
            "利润进度差": profit_gap,
            "状态": _budget_metric_status(income_gap, profit_gap),
        }
    )
    return row


def _fmt_budget_wan(value) -> str:
    return f"{_safe_float(value) / 10000:,.1f} 万"


def _fmt_budget_rate(value) -> str:
    if _budget_value_missing(value):
        return "-"
    return f"{_safe_float(value) * 100:.1f}%"


def _fmt_budget_gap(value) -> str:
    if _budget_value_missing(value):
        return "暂无进度差"
    gap = _safe_float(value)
    direction = "高于时间进度" if gap >= 0 else "低于时间进度"
    return f"{direction} {abs(gap) * 100:.1f}%"


def _budget_single_status(gap) -> str:
    if _budget_value_missing(gap):
        return "暂无预算"
    gap_value = _safe_float(gap)
    if gap_value < -1e-9:
        return "滞后"
    return "超前" if gap_value >= 0.02 else "正常"


def _budget_average_completion(overview_df: pd.DataFrame, metric: str = "income") -> float | None:
    if overview_df is None or overview_df.empty:
        return None
    rows = overview_df.copy()
    if "模块名称" in rows.columns:
        rows = rows[~rows["模块名称"].apply(_budget_is_pseudo_row_label)]
    if metric == "profit":
        budget_col = "利润预算"
        actual_col = "利润实际"
        completion_col = "利润完成率"
    else:
        budget_col = "收入预算"
        actual_col = "收入实际"
        completion_col = "收入完成率"
    values: list[float] = []
    if not {budget_col, actual_col, completion_col}.issubset(rows.columns):
        return None
    excluded_statuses = {"暂无预算", "待开业", "已取消", "待接入", "待匹配", "待确认"}
    for row in rows.to_dict("records"):
        if _budget_text(row.get("状态")) in excluded_statuses:
            continue
        budget = _safe_float(row.get(budget_col))
        if budget <= 0:
            continue
        if _budget_value_missing(row.get(actual_col)) or _budget_value_missing(row.get(completion_col)):
            continue
        values.append(_safe_float(row.get(completion_col)))
    if not values:
        return None
    return sum(values) / len(values)


def _fmt_budget_average_completion(value) -> str:
    if _budget_value_missing(value):
        return "暂无可比单位"
    return _fmt_budget_rate(value)


def _budget_kpi_cards_html(overview_df: pd.DataFrame, selected_month: str | int, progress: float) -> str:
    total = _budget_total_row(overview_df)
    income_average_completion = _budget_average_completion(overview_df, "income")
    profit_average_completion = _budget_average_completion(overview_df, "profit")
    income_completion = _fmt_budget_rate(total.get("收入完成率"))
    profit_completion = _fmt_budget_rate(total.get("利润完成率"))
    if profit_completion == "-":
        profit_completion = f"预算偏差 {_fmt_budget_gap(total.get('利润进度差'))}"
    return f"""
    <style>
      .budget-kpi-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0 16px;}}
      .budget-kpi-card{{background:#fff;border:1px solid rgba(148,163,184,.26);border-radius:14px;padding:18px 20px;box-shadow:0 10px 24px rgba(15,23,42,.05);min-height:160px;}}
      .budget-kpi-title{{font-size:15px;font-weight:800;color:#122033;margin-bottom:10px;}}
      .budget-kpi-value{{font-size:26px;font-weight:850;color:#0f172a;line-height:1.15;margin-bottom:6px;}}
      .budget-kpi-sub{{font-size:13px;color:#64748b;line-height:1.5;}}
      .budget-kpi-delta{{display:inline-block;margin-top:10px;padding:4px 8px;border-radius:999px;background:#eef6ff;color:#1d4ed8;font-size:12px;font-weight:750;}}
      .budget-kpi-progress{{height:8px;background:#e5eefb;border-radius:999px;overflow:hidden;margin:14px 0 8px;}}
      .budget-kpi-progress span{{display:block;height:100%;width:{min(max(progress, 0), 1) * 100:.2f}%;background:#2f7de1;border-radius:999px;}}
      @media (max-width: 980px){{.budget-kpi-grid{{grid-template-columns:1fr;}}}}
    </style>
    <div class="budget-kpi-grid">
      <div class="budget-kpi-card">
        <div class="budget-kpi-title">收入预算完成情况</div>
        <div class="budget-kpi-value">实际收入 {_html(_fmt_budget_wan(total.get("收入实际")))}</div>
        <div class="budget-kpi-sub">收入预算 {_html(_fmt_budget_wan(total.get("收入预算")))} · 收入完成率 {_html(income_completion)}</div>
        <div class="budget-kpi-sub">时间进度 {progress * 100:.1f}% · 平均完成度 {_html(_fmt_budget_average_completion(income_average_completion))}</div>
        <div class="budget-kpi-delta">{_html(_fmt_budget_gap(total.get("收入进度差")))}</div>
        <div class="budget-kpi-sub">状态：{_html(_budget_single_status(total.get("收入进度差")))}</div>
      </div>
      <div class="budget-kpi-card">
        <div class="budget-kpi-title">利润预算完成情况</div>
        <div class="budget-kpi-value">实际利润 {_html(_fmt_budget_wan(total.get("利润实际")))}</div>
        <div class="budget-kpi-sub">利润预算 {_html(_fmt_budget_wan(total.get("利润预算")))} · 利润完成率 {_html(profit_completion)}</div>
        <div class="budget-kpi-sub">时间进度 {progress * 100:.1f}% · 平均完成度 {_html(_fmt_budget_average_completion(profit_average_completion))}</div>
        <div class="budget-kpi-delta">{_html(_fmt_budget_gap(total.get("利润进度差")))}</div>
        <div class="budget-kpi-sub">状态：{_html(_budget_single_status(total.get("利润进度差")))}</div>
      </div>
    </div>
    """


def _render_budget_kpi_cards(overview_df: pd.DataFrame, selected_month: str | int, progress: float) -> None:
    _render_html(_budget_kpi_cards_html(overview_df, selected_month, progress))


def _budget_comparison_table_view(overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df is None or overview_df.empty:
        return pd.DataFrame()
    view = overview_df.copy()
    return pd.DataFrame(
        {
            "经营单位": view["模块名称"],
            "收入预算": pd.to_numeric(view["收入预算"], errors="coerce").fillna(0.0) / 10000,
            "收入实际": pd.to_numeric(view["收入实际"], errors="coerce").fillna(0.0) / 10000,
            "收入完成率": view["收入完成率"],
            "利润预算": pd.to_numeric(view["利润预算"], errors="coerce").fillna(0.0) / 10000,
            "利润实际": pd.to_numeric(view["利润实际"], errors="coerce").fillna(0.0) / 10000,
            "利润完成率": view["利润完成率"],
            "时间进度": view["时间进度"],
            "进度判断": view["状态"],
        }
    )


def _budget_cell_rate(value) -> str:
    return "-" if _budget_value_missing(value) else f"{_safe_float(value) * 100:.2f}%"


def _budget_cell_number(value) -> str:
    return f"{_safe_float(value):,.2f}"


def _budget_cell_html(value, kind: str = "text") -> str:
    if kind == "number":
        numeric = _safe_float(value)
        class_name = "budget-table-num budget-negative" if numeric < 0 else "budget-table-num"
        return f'<div class="{class_name}">{_html(_budget_cell_number(numeric))}</div>'
    if kind == "rate":
        if _budget_value_missing(value):
            return '<div class="budget-table-num">-</div>'
        numeric = _safe_float(value)
        class_name = "budget-table-num budget-negative" if numeric < 0 else "budget-table-num"
        return f'<div class="{class_name}">{numeric * 100:.2f}%</div>'
    if kind == "status":
        status = str(value or "")
        class_name = "budget-status-lag" if status == "滞后" else "budget-status-ok"
        return f'<div class="budget-status-cell"><span class="{class_name}">{_html(status)}</span></div>'
    return f'<div class="budget-table-text">{_html(value)}</div>'


def _budget_table_td_html(value, kind: str = "text", first: bool = False, total: bool = False) -> str:
    classes = ["budget-table-cell"]
    if first:
        classes.append("budget-table-first")
    if kind in {"number", "rate"}:
        classes.append("budget-table-num")
    elif kind == "status":
        classes.append("budget-table-status")
    if total:
        classes.append("budget-table-total-cell")

    if kind == "number":
        numeric = _safe_float(value)
        if numeric < 0:
            classes.append("budget-negative")
        content = _html(_budget_cell_number(numeric))
    elif kind == "rate":
        if _budget_value_missing(value):
            content = "-"
        else:
            numeric = _safe_float(value)
            if numeric < 0:
                classes.append("budget-negative")
            content = f"{numeric * 100:.2f}%"
    elif kind == "status":
        status = str(value or "")
        status_class = "budget-status-lag" if status == "滞后" else "budget-status-ok"
        content = f'<span class="{status_class}">{_html(status)}</span>'
    else:
        content = _html(value)
    return f'<td class="{" ".join(classes)}">{content}</td>'


def _render_budget_comparison_table(
    overview_df: pd.DataFrame,
    detail_df: pd.DataFrame,
    progress: float,
    period: str | None = None,
) -> None:
    view = _budget_comparison_table_view(overview_df)
    if view.empty:
        st.info("当前范围暂无预算或实际数据。")
        return
    headers = view.columns.tolist()
    header_html = "".join(f"<th>{_html(header)}</th>" for header in headers)
    body_rows = []
    for index, row in enumerate(view.to_dict("records")):
        module = str(row.get("经营单位") or "")
        is_total = module == "合计"
        row_class = "budget-total-row" if is_total else ""
        if module == "合计":
            first_cell = _budget_table_td_html(module, first=True, total=True)
        else:
            href = _app_query_href({"budget_drill": module})
            first_cell = (
                '<td class="budget-table-cell budget-table-first">'
                f'<a class="budget-module-link" target="_top" href="{_html(href)}">{_html(module)}</a>'
                '</td>'
            )
        cells = [first_cell]
        for column in headers[1:]:
            value = row.get(column)
            if column in {"收入预算", "收入实际", "利润预算", "利润实际"}:
                cells.append(_budget_table_td_html(value, "number", total=is_total))
            elif column in {"收入完成率", "利润完成率", "时间进度"}:
                cells.append(_budget_table_td_html(value, "rate", total=is_total))
            elif column == "进度判断":
                cells.append(_budget_table_td_html(value, "status", total=is_total))
            else:
                cells.append(_budget_table_td_html(value, total=is_total))
        body_rows.append(f'<tr class="{row_class}">{"".join(cells)}</tr>')
    st.markdown(
        f"""
        <style>
          .budget-table-toolbar{{display:flex;justify-content:flex-end;align-items:center;margin:-28px 0 6px;}}
          .budget-unit-note{{color:#64748b;font-size:12px;font-weight:750;}}
          .budget-table-scroll{{width:100%;overflow:auto;max-height:68vh;border:1px solid #d5deeb;border-radius:10px;background:#fff;box-shadow:0 10px 22px rgba(15,23,42,.04);}}
          .budget-comparison-table{{width:100%;min-width:1040px;border-collapse:collapse;table-layout:fixed;background:#fff;}}
          .budget-comparison-table th{{position:sticky;top:0;z-index:4;background:#eaf2ff;color:#10233f;font-size:13px;font-weight:850;text-align:right;padding:10px 12px;border-right:1px solid #d9e3f1;border-bottom:1px solid #c9d7e8;white-space:nowrap;}}
          .budget-comparison-table th:first-child{{left:0;z-index:7;text-align:left;width:17%;box-shadow:2px 0 0 rgba(148,163,184,.24);}}
          .budget-comparison-table th:nth-child(2),.budget-comparison-table th:nth-child(3),.budget-comparison-table th:nth-child(5),.budget-comparison-table th:nth-child(6){{width:12%;}}
          .budget-comparison-table th:nth-child(4),.budget-comparison-table th:nth-child(7),.budget-comparison-table th:nth-child(8){{width:10%;}}
          .budget-comparison-table th:last-child{{width:9%;border-right:0;text-align:center;}}
          .budget-comparison-table td{{background:#fff;color:#10233f;font-size:13px;padding:10px 12px;border-right:1px solid #e3ebf6;border-bottom:1px solid #e3ebf6;vertical-align:middle;line-height:1.35;}}
          .budget-comparison-table tr:nth-child(even) td{{background:#fbfdff;}}
          .budget-comparison-table td:last-child{{border-right:0;}}
          .budget-table-first{{position:sticky;left:0;z-index:3;text-align:left;font-weight:800;background:#fff!important;box-shadow:2px 0 0 rgba(148,163,184,.18);}}
          .budget-comparison-table tr:nth-child(even) .budget-table-first{{background:#fbfdff!important;}}
          .budget-table-num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}}
          .budget-table-status{{text-align:center;}}
          .budget-module-link{{display:inline;color:#1d4ed8;font-weight:850;text-decoration:none;border-bottom:1px solid rgba(29,78,216,.35);}}
          .budget-module-link:hover{{color:#174ea6;border-bottom-color:#174ea6;}}
          .budget-negative{{color:#d92d20!important;background:#fff7f7!important;}}
          .budget-status-ok,.budget-status-lag{{display:inline-flex;align-items:center;justify-content:center;min-width:44px;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:850;}}
          .budget-status-ok{{background:#ecfdf3;color:#027a48;}}
          .budget-status-lag{{background:#fff1f0;color:#d92d20;}}
          .budget-total-row td{{font-weight:900;background:#f3f7ff!important;border-top:2px solid #c9d7e8;}}
          .budget-total-row .budget-table-first{{background:#f3f7ff!important;}}
        </style>
        <div class="budget-table-toolbar"><span class="budget-unit-note">单位：万元</span></div>
        <div class="budget-table-scroll">
          <table class="budget-comparison-table">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{"".join(body_rows)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
    drill_module = _get_query_param("budget_drill")
    valid_modules = set(view["经营单位"].astype(str)) - {"合计"}
    if drill_module in valid_modules:
        _clear_query_param("budget_drill")
        show_budget_drilldown_dialog(drill_module, detail_df, progress, period)


def _budget_policy_note(progress: float) -> str:
    return (
        f"说明：全年预算按 100% 计算；月进度 = 月份 / 12；当前时间进度为 {progress * 100:.2f}%；"
        "实际数来源为收入成本费用表本年累计；模块/集团按当前范围抵消内部管理服务费；"
        "收入、利润完成率分别对比时间进度；平均完成度仅统计正预算且有实际数的经营单位；"
        "负利润预算按减亏进度单独判断，避免亏损扩大被误判为超前。"
    )


def _budget_module_bridge(detail_df: pd.DataFrame, module_name: str) -> dict:
    if detail_df is None or detail_df.empty:
        return {}
    context = detail_df.attrs.get("budget_internal_adjustments", {}) if hasattr(detail_df, "attrs") else {}
    if not isinstance(context, dict) or not context:
        return {}
    module = _budget_text(module_name)
    module_rows = detail_df[detail_df["module"].astype(str) == module].copy() if "module" in detail_df.columns else pd.DataFrame()
    raw_income = _safe_float(pd.to_numeric(module_rows.get("收入实际", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    raw_profit = _safe_float(pd.to_numeric(module_rows.get("利润实际", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    adjustment = _safe_float((context.get("module_adjustments") or {}).get(module))
    if module == "合计":
        adjustment = _safe_float(context.get("total_adjustment"))
    if abs(adjustment) <= 1e-9:
        return {}
    return {
        "raw_income": raw_income,
        "income_adjustment": adjustment,
        "adjusted_income": raw_income - adjustment,
        "raw_profit": raw_profit,
        "adjusted_profit": raw_profit,
    }


def _budget_bridge_note_html(module_name: str, bridge: dict) -> str:
    if not bridge:
        return ""
    return f"""
    <div class="budget-bridge-note" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 12px;padding:10px 12px;border:1px solid #dbe5f2;border-radius:10px;background:#f8fbff;color:#334155;font-size:12px;font-weight:750;">
      <span>{_html(module_name)}主表采用合并口径；下钻为单体原始本年累计。</span>
      <span>单体收入合计 <b>{_html(_fmt_budget_wan(bridge.get("raw_income")))}</b></span>
      <span>减内部抵消 <b>{_html(_fmt_budget_wan(bridge.get("income_adjustment")))}</b></span>
      <span>主表收入 <b>{_html(_fmt_budget_wan(bridge.get("adjusted_income")))}</b></span>
      <span>纯内部交易收入和成本同步抵消，利润 <b>{_html(_fmt_budget_wan(bridge.get("adjusted_profit")))}</b></span>
    </div>
    """


def _budget_quality_center_drilldown_view(
    targets_df: pd.DataFrame,
    progress: float,
    actual_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if targets_df is None or targets_df.empty:
        return pd.DataFrame(
            columns=["校区名称", "全年收入预算目标", "实际收入", "收入完成率", "时间进度", "进度差", "状态"]
        )
    source_actual = actual_df if actual_df is not None else _budget_empty_quality_center_actual_frame()
    matched = match_quality_center_campus_actuals(targets_df, source_actual)
    rows = []
    for row in matched.to_dict("records"):
        budget = _safe_float(row.get("income_budget"))
        status = _budget_text(row.get("match_status"))
        if status == "已匹配":
            actual = _safe_float(row.get("actual_income"))
            completion = actual / budget if abs(budget) >= 1e-9 else None
            gap = completion - progress if not _budget_value_missing(completion) else None
            final_status = _budget_single_status(gap)
        elif status == "待确认":
            actual = "待确认"
            completion = "待确认"
            gap = "待确认"
            final_status = "待确认"
        elif status in {"待开业", "已取消"}:
            actual = status
            completion = "-"
            gap = "-"
            final_status = status
        else:
            actual = "待匹配"
            completion = "待匹配"
            gap = "待匹配"
            final_status = "待匹配"
        rows.append(
            {
                "校区名称": row.get("campus_name"),
                "全年收入预算目标": budget,
                "实际收入": actual,
                "收入完成率": completion,
                "时间进度": progress,
                "进度差": gap,
                "状态": final_status,
            }
        )
    view = pd.DataFrame(rows)
    return view[["校区名称", "全年收入预算目标", "实际收入", "收入完成率", "时间进度", "进度差", "状态"]]


def _budget_drill_cell_html(value, kind: str = "text") -> str:
    if kind == "money":
        if isinstance(value, str):
            return f'<td class="budget-drill-text">{_html(value)}</td>'
        numeric = _safe_float(value) / 10000
        cls = "budget-drill-num budget-negative" if numeric < 0 else "budget-drill-num"
        return f'<td class="{cls}">{_html(f"{numeric:,.2f}")}</td>'
    if kind == "rate":
        if isinstance(value, str) or _budget_value_missing(value):
            return f'<td class="budget-drill-num">{_html(value if isinstance(value, str) else "-")}</td>'
        numeric = _safe_float(value)
        cls = "budget-drill-num budget-negative" if numeric < 0 else "budget-drill-num"
        return f'<td class="{cls}">{numeric * 100:.2f}%</td>'
    if kind == "status":
        text_value = _budget_text(value)
        if text_value in {"待匹配", "待确认", "待开业", "已取消"}:
            cls = "budget-drill-status-wait"
        elif text_value == "滞后":
            cls = "budget-drill-status-lag"
        else:
            cls = "budget-drill-status-ok"
        return f'<td class="budget-drill-center"><span class="{cls}">{_html(text_value)}</span></td>'
    return f'<td class="budget-drill-text">{_html(value)}</td>'


def _budget_drill_table_html(
    display_df: pd.DataFrame,
    money_cols: set[str],
    rate_cols: set[str],
    status_col: str = "状态",
) -> str:
    if display_df is None or display_df.empty:
        return '<div class="budget-drill-empty">暂无下钻明细。</div>'
    headers = "".join(f"<th>{_html(column)}</th>" for column in display_df.columns)
    body_rows = []
    for row in display_df.to_dict("records"):
        cells = []
        for column in display_df.columns:
            value = row.get(column)
            if column in money_cols:
                cells.append(_budget_drill_cell_html(value, "money"))
            elif column in rate_cols:
                cells.append(_budget_drill_cell_html(value, "rate"))
            elif column == status_col:
                cells.append(_budget_drill_cell_html(value, "status"))
            else:
                cells.append(_budget_drill_cell_html(value, "text"))
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <style>
      .budget-drill-wrap{{margin-top:10px;overflow:auto;max-height:64vh;}}
      .budget-drill-unit{{display:block;text-align:right;font-size:12px;font-weight:750;color:#64748b;margin-bottom:6px;}}
      .budget-drill-table{{width:100%;min-width:760px;border-collapse:collapse;background:#fff;border:1px solid #dbe5f2;border-radius:10px;overflow:hidden;}}
      .budget-drill-table th{{position:sticky;top:0;z-index:4;background:#edf4ff;color:#10233f;font-size:13px;font-weight:850;text-align:center;padding:9px 10px;border:1px solid #dbe5f2;white-space:nowrap;}}
      .budget-drill-table th:first-child{{left:0;z-index:7;box-shadow:2px 0 0 rgba(148,163,184,.24);}}
      .budget-drill-table td{{font-size:13px;padding:9px 10px;border:1px solid #e4ebf5;}}
      .budget-drill-table td:first-child{{position:sticky;left:0;z-index:3;background:#fff;box-shadow:2px 0 0 rgba(148,163,184,.18);}}
      .budget-drill-table tr:nth-child(even) td:first-child{{background:#fbfdff;}}
      .budget-drill-text{{color:#10233f;text-align:left;font-weight:700;}}
      .budget-drill-num{{color:#10233f;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}}
      .budget-drill-center{{text-align:center;}}
      .budget-drill-status-ok,.budget-drill-status-lag,.budget-drill-status-wait{{display:inline-flex;align-items:center;justify-content:center;min-width:52px;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:850;}}
      .budget-drill-status-ok{{background:#ecfdf3;color:#027a48;}}
      .budget-drill-status-lag{{background:#fff1f0;color:#d92d20;}}
      .budget-drill-status-wait{{background:#f1f5f9;color:#475569;}}
      .budget-drill-empty{{padding:14px;border:1px dashed #cbd5e1;border-radius:10px;color:#64748b;background:#fff;}}
    </style>
    <div class="budget-drill-unit">单位：万元</div>
    <div class="budget-drill-wrap">
      <table class="budget-drill-table">
        <thead><tr>{headers}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """


def _budget_drill_summary_html(title: str, budget, actual, completion, progress: float, status: str) -> str:
    completion_text = completion if isinstance(completion, str) else _fmt_budget_rate(completion)
    actual_text = actual if isinstance(actual, str) else _fmt_budget_wan(actual)
    return f"""
    <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:10px 0 12px;">
      <div style="background:#f8fbff;border:1px solid #dbe5f2;border-radius:10px;padding:10px;"><b>{_html(title)}</b></div>
      <div style="background:#fff;border:1px solid #dbe5f2;border-radius:10px;padding:10px;">预算目标<br><b>{_html(_fmt_budget_wan(budget))}</b></div>
      <div style="background:#fff;border:1px solid #dbe5f2;border-radius:10px;padding:10px;">实际<br><b>{_html(actual_text)}</b></div>
      <div style="background:#fff;border:1px solid #dbe5f2;border-radius:10px;padding:10px;">完成率 / 时间<br><b>{_html(completion_text)} / {progress * 100:.2f}%</b></div>
      <div style="background:#fff;border:1px solid #dbe5f2;border-radius:10px;padding:10px;">状态<br><b>{_html(status)}</b></div>
    </div>
    """


@st.dialog("经营单位预算下钻", width="large")
def show_budget_drilldown_dialog(
    module_name: str,
    detail_df: pd.DataFrame,
    progress: float,
    period: str | None = None,
) -> None:
    if str(module_name) == "东莞素质中心":
        st.markdown("#### 经营单位预算下钻 - 东莞素质中心")
        targets = read_quality_center_campus_budget_targets()
        if targets.empty:
            st.info("未读取到东莞素质中心校区预算目标。")
        else:
            actuals = load_quality_center_actual_income(period or "")
            matched = match_quality_center_campus_actuals(targets, actuals)
            display = _budget_quality_center_drilldown_view(targets, progress, actuals)
            matched_display = display[display["实际收入"].apply(lambda value: not isinstance(value, str))]
            total_budget = _safe_float(pd.to_numeric(display["全年收入预算目标"], errors="coerce").fillna(0.0).sum())
            total_actual = _safe_float(pd.to_numeric(matched_display["实际收入"], errors="coerce").fillna(0.0).sum())
            completion = total_actual / total_budget if abs(total_budget) >= 1e-9 and len(matched_display) else "待匹配"
            gap = completion - progress if not isinstance(completion, str) else None
            status = _budget_single_status(gap) if gap is not None else "待匹配"
            _render_html(_budget_drill_summary_html("校区收入目标", total_budget, total_actual if len(matched_display) else "待匹配", completion, progress, status))
            bridge_html = _budget_bridge_note_html(module_name, _budget_module_bridge(detail_df, module_name))
            if bridge_html:
                _render_html(bridge_html)
            _render_html(
                _budget_drill_table_html(
                    display,
                    money_cols={"全年收入预算目标", "实际收入"},
                    rate_cols={"收入完成率", "时间进度", "进度差"},
                )
            )
            unmatched = quality_center_unmatched_items(matched)
            if not unmatched.empty:
                with st.expander("待确认/未匹配校区清单", expanded=False):
                    st.dataframe(unmatched, use_container_width=True, hide_index=True)
            st.caption(f"预算目标来源：{BUDGET_QUALITY_CENTER_SHEET_NAME}，优先读取表头中的“合并收入/合计/目标/全年”列；当前表为第 N 列“合并收入”。")
        if st.button("关闭明细", use_container_width=True):
            st.rerun()
        return

    st.markdown(f"#### 经营单位预算下钻 - {module_name}")
    drill_df = detail_df[detail_df["module"].astype(str) == str(module_name)].copy() if len(detail_df) else pd.DataFrame()
    detail_view = _budget_module_drilldown_view(module_name, detail_df, progress)
    total_budget = _safe_float(pd.to_numeric(drill_df.get("收入预算", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    total_actual = _safe_float(pd.to_numeric(drill_df.get("收入实际", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    completion, gap = _budget_metric_progress(total_actual, total_budget, progress, "income")
    _render_html(_budget_drill_summary_html("公司收入进度", total_budget, total_actual, completion, progress, _budget_single_status(gap)))
    bridge_html = _budget_bridge_note_html(module_name, _budget_module_bridge(detail_df, module_name))
    if bridge_html:
        _render_html(bridge_html)
    _render_html(
        _budget_drill_table_html(
            detail_view,
            money_cols={"收入预算", "收入实际", "利润预算", "利润实际"},
            rate_cols=set(),
        )
    )
    if st.button("关闭明细", use_container_width=True):
        st.rerun()


def render_budget_dashboard():
    st.markdown('<div class="page-header">全面预算</div>', unsafe_allow_html=True)
    st.caption(f"{BUDGET_VERSION} · 第一版只看收入预算、利润预算和经营单位完成进度。")

    actual_months_by_year = _budget_actual_period_months()
    years = sorted(set(actual_months_by_year) | {_home_budget_plan_year() or "2026"}, reverse=True)
    if not years:
        years = ["2026"]
    month_options, has_actual_months = _prepare_budget_year_month_state(years, actual_months_by_year)
    c1, c2, c3, c4, c5 = st.columns([0.85, 0.85, 1.15, 1.55, 0.95], gap="small")
    with c1:
        selected_year = st.selectbox("年份", years, key="budget_year")
        if selected_year != st.session_state.get("_budget_last_seen_year"):
            current_months = actual_months_by_year.get(selected_year, [])
            if current_months:
                st.session_state["budget_month"] = current_months[-1]
                month_options = current_months
                has_actual_months = True
            else:
                month_options = [f"{idx:02d}" for idx in range(1, 13)]
                st.session_state["budget_month"] = _budget_default_month(month_options, False)
                has_actual_months = False
    with c2:
        if st.session_state.get("budget_month") not in month_options:
            st.session_state["budget_month"] = _budget_default_month(month_options, bool(actual_months_by_year.get(selected_year)))
        selected_month = st.selectbox("月份", month_options, key="budget_month")
        st.session_state["_budget_last_seen_year"] = selected_year
    with c3:
        st.selectbox("经营单位", ["1 集团"], key="budget_scope", disabled=True)
    with c4:
        st.selectbox("预算版本", [BUDGET_VERSION], key="budget_version", disabled=True)
    with c5:
        st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
        st.button("查询预算", type="primary", icon=":material/search:", key="budget_query", use_container_width=True)

    period = f"{selected_year}{selected_month}"
    if not has_actual_months:
        st.info(f"{selected_year} 年暂无可用于预算实际数的收入成本费用表本年累计数据，月份暂按安全默认值显示。")
    plan_df = read_budget_plan()
    if plan_df.empty:
        st.warning(_budget_missing_file_message())
    actual_df = load_budget_actuals(period)
    overview_df, detail_df = build_budget_completion_data(plan_df, actual_df, selected_month)
    progress = budget_time_progress(selected_month)

    tab_overview, tab_income, tab_profit, tab_unit = st.tabs(["预算总览", "收入预算", "利润预算", "经营单位对比"])
    with tab_overview:
        _render_budget_kpi_cards(overview_df, selected_month, progress)
        with st.container(border=True):
            st.markdown("#### 经营单位预算进度对比")
            _render_budget_comparison_table(overview_df, detail_df, progress, period)
            st.caption(_budget_policy_note(progress))

    with tab_income:
        income_view = _budget_overview_view(overview_df)
        columns = ["模块名称", "收入预算", "收入实际", "收入进度", "状态"]
        _render_budget_dataframe(income_view[[column for column in columns if column in income_view.columns]], height=420)

    with tab_profit:
        profit_view = _budget_overview_view(overview_df)
        columns = ["模块名称", "利润预算", "利润实际", "利润进度", "状态"]
        _render_budget_dataframe(profit_view[[column for column in columns if column in profit_view.columns]], height=420)

    with tab_unit:
        if len(detail_df):
            display = _budget_detail_view(detail_df, progress).copy()
            display.insert(0, "模块名称", detail_df["module"].astype(str).tolist())
        else:
            display = detail_df
        _render_budget_dataframe(display, height=520)


def render_cashflow():
    st.markdown('<div class="page-header">💵 现金流量表</div>', unsafe_allow_html=True)
    years, months = _get_year_month_options()
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        companies = st.session_state.get("companies", pd.DataFrame())
        company_dict = companies.set_index("code")["name"].to_dict() if not companies.empty else {}
        sel_company = st.selectbox(
            "选择公司",
            companies["code"].tolist() if not companies.empty else [],
            format_func=lambda x: f"{x} - {company_dict.get(x, x)}",
            key="cf_c",
        )
    with c2:
        sel_year = st.selectbox("年份", [""] + years if years else ["2026"], key="cf_y")
    with c3:
        sel_month = st.selectbox("月份", [""] + months if months else ["03"], key="cf_m")
    sel_period = (sel_year + sel_month) if sel_year and sel_month else ""

    if st.button("生成报表", type="primary", icon=":material/request_quote:", use_container_width=True):
        if not sel_company or not sel_period:
            st.toast("请选择公司和期间", icon="⚠️"); return
        with st.spinner("⏳ 生成中..."):
            df = get_cashflow(sel_company, sel_period)
            if len(df) > 0:
                st.toast("报表生成成功！", icon="✅")
                if "项目" in df.columns:
                    df_display = df[[c for c in ["行次", "项目", "期末余额", "是否小计", "缩进层级"] if c in df.columns]].copy()
                else:
                    df_display = _cn_cols(df, {
                        "account_code": "科目编码",
                        "account_name": "科目名称",
                        "debit_amount": "借方发生额",
                        "credit_amount": "贷方发生额",
                        "ending_balance": "期末余额",
                    })
                st.dataframe(df_display, use_container_width=True, hide_index=True, height=500, column_config={
                    "借方发生额": st.column_config.NumberColumn("借方发生额", format="%,.2f"),
                    "贷方发生额": st.column_config.NumberColumn("贷方发生额", format="%,.2f"),
                    "期末余额": st.column_config.NumberColumn("期末余额", format="%,.2f"),
                })
                with st.spinner("⏳ 生成导出文件..."):
                    fpath = export_cashflow(
                        df_display,
                        _company_label(sel_company, company_dict),
                        sel_period,
                    )
                    excel_bytes = _read_export_bytes(fpath)
                st.download_button(
                    "📥 导出 Excel",
                    data=excel_bytes,
                    file_name=f"现金流量表_{sel_company}_{sel_period}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_cf",
                )
            else:
                st.toast("未生成数据", icon="⚠️")

DETAIL_QUERY_HTML_ROW_LIMIT = 1000


def render_detail_tables():
    st.markdown('<div class="page-header">📑 明细表查询</div>', unsafe_allow_html=True)
    table_type = st.selectbox("选择明细表类型", ["损益明细表", "收入人次表", "非学科费用分配表", "管理中心部门收入成本费用表", "非学科课酬表"])
    years, months = _get_year_month_options()
    companies = st.session_state.get("companies", pd.DataFrame())
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1: sel_company = st.selectbox("公司（可选）", [""] + companies["code"].tolist() if not companies.empty else [""], key="dt_c")
    with col2: sel_year = st.selectbox("年份", [""] + years if years else [""], key="dt_y")
    with col3: sel_month = st.selectbox("月份", [""] + months if months else [""], key="dt_m")
    sel_period = (sel_year + sel_month) if sel_year and sel_month else None
    if st.button("查询", type="primary", icon=":material/search:", use_container_width=True):
        with st.spinner("⏳ 查询中..."):
            query_map = {"损益明细表": get_pl_detail, "收入人次表": get_revenue_volume, "非学科费用分配表": get_non_subject_allocation, "管理中心部门收入成本费用表": get_mgmt_dept_income_cost, "非学科课酬表": get_non_subject_teaching_fee}
            func = query_map.get(table_type)
            df = func(sel_company or None, sel_period) if func else pd.DataFrame()
            if len(df) > 0:
                st.toast(f"✅ 查询成功！共获取 {len(df)} 条记录")
                cn_map = {"company_code": "公司编码", "period": "期间", "item_code": "项目编码", "item_name": "项目名称", "category": "类别", "amount": "金额", "dept_code": "部门编码", "dept_name": "部门名称", "product_line": "产品线", "data_period": "数据期间", "business_period": "业务期间", "year": "年份", "month": "月份", "calendar_quarter": "自然季度", "source_quarter_label": "源季度标签", "campus_name": "校区名称", "grade": "年级", "subject": "科目", "customer_count": "人次", "revenue_amount": "收入金额", "unit_price": "单价", "source_file": "源文件", "source_sheet": "源Sheet", "cost_center": "成本中心", "allocated_amount": "分配金额", "teacher_name": "教师姓名", "course_type": "课程类型", "hours": "课时", "rate": "单价", "total_amount": "合计"}
                df = _cn_cols(df, cn_map)
                config = {}
                for c in df.select_dtypes(include=['float64', 'int64']).columns:
                    if c not in ["期间", "人次", "课时"]:
                        config[c] = st.column_config.NumberColumn(c, format="%,.2f")
                _render_detail_query_result(df, config, table_type, sel_company or None, sel_period)
            else:
                st.toast("未查询到数据", icon="⚠️")


def _detail_query_download_filename(table_type: str, company_code: str | None, period: str | None) -> str:
    parts = [str(table_type or "明细表查询")]
    if company_code:
        parts.append(str(company_code))
    if period:
        parts.append(str(period))
    raw = "_".join(parts)
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", raw).strip("_")
    return f"{safe or '明细表查询'}.csv"


def _render_detail_query_result(
    df: pd.DataFrame,
    column_config: dict | None = None,
    table_type: str = "",
    company_code: str | None = None,
    period: str | None = None,
) -> None:
    if len(df) > DETAIL_QUERY_HTML_ROW_LIMIT:
        st.warning(
            f"本次查询返回 {len(df):,} 行，已启用大结果集保护：完整结果用原生表格展示，"
            f"避免一次性生成过大的 HTML；如需冻结首列预览，请选择公司或期间缩小到 {DETAIL_QUERY_HTML_ROW_LIMIT:,} 行以内。"
        )
        download_name = _detail_query_download_filename(table_type, company_code, period)
        st.download_button(
            "导出完整查询结果 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=download_name,
            mime="text/csv",
            use_container_width=True,
            key=f"detail_query_export_{download_name}_{len(df)}",
        )
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config=column_config or {},
        )
        return
    st.markdown(_detail_query_table_html(df), unsafe_allow_html=True)


def _detail_query_table_html(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<div class="detail-query-empty">暂无明细数据。</div>'
    numeric_cols = set(df.select_dtypes(include=["float64", "int64", "int32", "float32"]).columns)
    min_width = max(920, len(df.columns) * 138)
    header_html = "".join(f"<th>{_html(column)}</th>" for column in df.columns)
    body_rows = []
    for record in df.to_dict("records"):
        cells = []
        for column in df.columns:
            value = record.get(column)
            is_numeric = column in numeric_cols and pd.notna(value)
            if is_numeric:
                try:
                    display = f"{float(value):,.2f}"
                except (TypeError, ValueError):
                    display = str(value)
                cls = "detail-query-num"
            else:
                display = "" if pd.isna(value) else str(value)
                cls = "detail-query-text"
            cells.append(f'<td class="{cls}" title="{_html(display)}">{_html(display)}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <style>
      .detail-query-table-wrap{{width:100%;overflow:auto;max-height:70vh;border:1px solid #dbe5f2;border-radius:8px;background:#fff;}}
      .detail-query-table{{width:100%;min-width:{min_width}px;border-collapse:collapse;table-layout:fixed;color:#10233f;font-size:13px;}}
      .detail-query-table th,.detail-query-table td{{border:1px solid #dbe5f2;padding:8px 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:middle;}}
      .detail-query-table th{{position:sticky;top:0;z-index:4;background:#eaf2ff;color:#10233f;text-align:center;font-weight:850;}}
      .detail-query-table th:first-child{{left:0;z-index:7;box-shadow:2px 0 0 rgba(148,163,184,.24);}}
      .detail-query-table td:first-child{{position:sticky;left:0;z-index:3;background:#fff;box-shadow:2px 0 0 rgba(148,163,184,.18);}}
      .detail-query-table tr:nth-child(even) td{{background:#fbfdff;}}
      .detail-query-table tr:nth-child(even) td:first-child{{background:#fbfdff;}}
      .detail-query-num{{text-align:right;font-variant-numeric:tabular-nums;}}
      .detail-query-text{{text-align:center;}}
      .detail-query-empty{{padding:14px;border:1px dashed #cbd5e1;border-radius:8px;color:#64748b;background:#fff;}}
    </style>
    <div class="detail-query-table-wrap">
      <table class="detail-query-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """

def _render_structure_table(df: pd.DataFrame, external: bool = False) -> None:
    display = df.copy()
    display["投资占比"] = display["ownership_pct"].map(lambda value: f"{float(value or 0):.2f}%")
    display["是否控制"] = display["has_control"].astype(int).map({1: "是", 0: "否"}).fillna("否")
    if external:
        view = display.rename(columns={
            "display_name": "项目",
            "investor_codes": "投资主体",
            "business_type": "业态类型",
            "region": "区域",
            "investment_category": "投资分类",
        })[["项目", "投资主体", "投资占比", "是否控制", "投资分类", "业态类型", "区域"]]
    else:
        view = display.rename(columns={
            "display_name": "层级展示",
            "parent_name": "上级公司",
            "display_module": "所属模块",
            "investment_category": "投资分类",
            "is_operational": "运营主体",
            "is_consolidated": "合并范围",
        })[["层级展示", "所属模块", "上级公司", "投资占比", "投资分类", "运营主体", "合并范围"]]
    st.dataframe(view, use_container_width=True, hide_index=True)


def render_company_hierarchy():
    """公司层级管理页面"""
    st.markdown('<div class="page-header">🌳 公司层级管理</div>', unsafe_allow_html=True)

    # ---------- 导入 ----------
    st.markdown("##### 📤 导入公司层级")
    uploaded_file = st.file_uploader("上传公司清单 Excel", type=["xlsx", "xls"], key="hierarchy_upload")
    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        try:
            result = import_companies_from_excel(tmp_path)
            if result["success"]:
                st.toast(f"✅ 成功导入 {result['total']} 家公司")
            else:
                for e in result.get("errors", []):
                    st.error(e)
        finally:
            os.unlink(tmp_path)
        st.rerun()
    # ---------- 组织分类折叠视图 ----------
    st.markdown("##### 🗂️ 组织分类折叠视图")
    try:
        structure_df = get_company_structure_view()
        if len(structure_df) > 0:
            managed_df = structure_df[structure_df["management_category"] == MANAGED_CATEGORY]
            external_df = structure_df[structure_df["management_category"] == EXTERNAL_CATEGORY]

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("实控公司", f"{len(managed_df)} 家")
            col_m2.metric("对外投资公司", f"{len(external_df)} 家")
            col_m3.metric("业务模块", f"{managed_df['display_module'].nunique()} 个")

            with st.expander(f"实控公司（全资子公司 / 实际管理运营公司，共 {len(managed_df)} 家）", expanded=True):
                module_order = MANAGED_MODULES + [FALLBACK_MANAGED_MODULE]
                for module in module_order:
                    module_df = managed_df[managed_df["display_module"] == module]
                    if module_df.empty:
                        continue
                    st.markdown(f"###### {module}（{len(module_df)} 家）")
                    _render_structure_table(module_df, external=False)

            with st.expander(f"对外投资公司（单项目展示，共 {len(external_df)} 家）", expanded=True):
                if external_df.empty:
                    st.info("暂无对外投资公司。将投资占比中的“是否控制”改为“否”后，会归入这里。")
                else:
                    _render_structure_table(external_df, external=True)
        else:
            st.info("暂无可展示的公司结构数据")
    except Exception as e:
        st.error(f"组织分类视图加载失败: {e}")
    # ---------- 编辑表格 ----------
    st.markdown("##### ✏️ 编辑公司信息（直接修改表格后点保存）")

    try:
        tree = get_company_tree()
        if len(tree) > 0:
            # 准备可编辑的 DataFrame
            edit_df = tree[["code", "name", "parent_code", "level", "is_consolidated", "is_leaf", "tree_path"]].copy()
            # 合并范围转为文字方便编辑
            edit_df["is_consolidated"] = edit_df["is_consolidated"].astype(str).replace({"1": "是", "0": "否"})

            edited = st.data_editor(
                edit_df,
                use_container_width=True,
                hide_index=True,
                height=500,
                column_config={
                    "code": st.column_config.TextColumn("公司编码", width="small", disabled=True),
                    "name": st.column_config.TextColumn("公司名称", width="medium", required=True),
                    "parent_code": st.column_config.SelectboxColumn("上级编码", width="small",
                        options=[""] + tree["code"].tolist(), required=False),
                    "level": st.column_config.NumberColumn("层级", width="small", disabled=True),
                    "is_consolidated": st.column_config.SelectboxColumn("合并范围", width="small",
                        options=["是", "否"]),
                    "is_leaf": st.column_config.TextColumn("末级", width="small", disabled=True),
                    "tree_path": st.column_config.TextColumn("路径", width="medium", disabled=True),
                },
                disabled=["code", "level", "is_leaf", "tree_path"],
                key="company_editor",
            )

            if st.button("💾 保存修改", type="primary", use_container_width=True):
                session = get_session()
                try:
                    for _, row in edited.iterrows():
                        consolidated = 1 if str(row.get("is_consolidated", "是")) == "是" else 0
                        parent = str(row.get("parent_code", "")).strip() or None
                        session.execute(
                            text("""UPDATE companies SET name = :n, parent_code = :p,
                                    is_consolidated = :c WHERE code = :code"""),
                            {"n": str(row["name"]).strip(), "p": parent,
                             "c": consolidated, "code": row["code"]}
                        )
                    session.commit()
                    # 重建树路径
                    roots = session.execute(
                        text("SELECT code FROM companies WHERE parent_code IS NULL OR parent_code = ''")
                    ).fetchall()
                    for r in roots:
                        rebuild_tree_path(r[0])
                    session.close()
                    st.session_state.companies = get_companies()
                    st.toast("✅ 修改已保存，树路径已重建")
                    st.rerun()
                except Exception as ex:
                    session.rollback()
                    session.close()
                    st.error(f"保存失败: {ex}")
        else:
            st.info("暂无公司信息")
    except Exception as e:
        st.info(f"暂无公司信息: {e}")
    # ---------- 公司属性维度 ----------
    st.markdown("##### 🧭 组织架构与公司属性维护")
    try:
        dim_df = get_company_dimensions()
        if len(dim_df) > 0:
            dim_edit = dim_df.rename(columns={
                "company_id": "公司编码",
                "company_name": "公司名称",
                "business_group": "所属板块",
                "business_type": "业态类型",
                "region": "所属区域",
                "is_operational": "运营主体",
                "parent_code": "上级编码",
                "level": "层级",
                "tree_path": "路径",
            })
            visible_cols = ["公司编码", "公司名称", "所属板块", "业态类型", "所属区域", "运营主体", "上级编码", "层级"]
            edited_dim = st.data_editor(
                dim_edit[visible_cols],
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={
                    "公司编码": st.column_config.TextColumn("公司编码", width="small", disabled=True),
                    "公司名称": st.column_config.TextColumn("公司名称", width="medium", disabled=True),
                    "所属板块": st.column_config.SelectboxColumn("所属板块", options=BUSINESS_GROUP_OPTIONS, width="small"),
                    "业态类型": st.column_config.SelectboxColumn("业态类型", options=BUSINESS_TYPE_OPTIONS, width="small"),
                    "所属区域": st.column_config.SelectboxColumn("所属区域", options=REGION_OPTIONS, width="small"),
                    "运营主体": st.column_config.SelectboxColumn("运营主体", options=OPERATIONAL_OPTIONS, width="small"),
                    "上级编码": st.column_config.TextColumn("上级编码", width="small", disabled=True),
                    "层级": st.column_config.NumberColumn("层级", width="small", disabled=True),
                },
                disabled=["公司编码", "公司名称", "上级编码", "层级"],
                key="company_dimension_editor",
            )
            if st.button("💾 保存公司属性", type="primary", use_container_width=True):
                try:
                    saved = save_company_dimensions(edited_dim)
                    st.toast(f"✅ 已保存 {saved} 家公司属性")
                    st.rerun()
                except Exception as ex:
                    st.error(f"保存公司属性失败: {ex}")
        else:
            st.info("暂无公司维度数据")
    except Exception as e:
        st.error(f"公司属性维度加载失败: {e}")
    # ---------- 投资占比与控制关系 ----------
    st.markdown("##### 🧾 投资占比与控制关系维护")
    try:
        ownership_df = get_ownership_grid()
        companies_for_options = st.session_state.get("companies", pd.DataFrame())
        if companies_for_options is None or companies_for_options.empty:
            companies_for_options = get_companies()
        company_options = [""] + companies_for_options["code"].astype(str).tolist() if not companies_for_options.empty else [""]

        ownership_edit = ownership_df.rename(columns={
            "parent_code": "母公司编码",
            "parent_name": "母公司名称",
            "sub_code": "子公司编码",
            "sub_name": "子公司名称",
            "business_group": "所属板块",
            "business_type": "业态类型",
            "ownership_pct": "投资占比(%)",
            "investment_category": "投资分类",
            "effective_date": "生效日期",
            "expiration_date": "失效日期",
            "is_control": "是否控制",
        })
        visible_cols = [
            "母公司编码", "母公司名称", "子公司编码", "子公司名称",
            "所属板块", "业态类型", "投资占比(%)", "投资分类",
            "生效日期", "失效日期", "是否控制",
        ]
        edited_ownership = st.data_editor(
            ownership_edit[visible_cols],
            use_container_width=True,
            hide_index=True,
            height=520,
            num_rows="dynamic",
            column_config={
                "母公司编码": st.column_config.SelectboxColumn("母公司编码", options=company_options, width="small"),
                "母公司名称": st.column_config.TextColumn("母公司名称", width="medium", disabled=True),
                "子公司编码": st.column_config.SelectboxColumn("子公司编码", options=company_options, width="small"),
                "子公司名称": st.column_config.TextColumn("子公司名称", width="medium", disabled=True),
                "所属板块": st.column_config.TextColumn("所属板块", width="small", disabled=True),
                "业态类型": st.column_config.TextColumn("业态类型", width="small", disabled=True),
                "投资占比(%)": st.column_config.NumberColumn("投资占比(%)", min_value=0.0, max_value=100.0, step=0.01, format="%.2f", width="small"),
                "投资分类": st.column_config.TextColumn("投资分类", width="small", disabled=True),
                "生效日期": st.column_config.TextColumn("生效日期", width="small"),
                "失效日期": st.column_config.TextColumn("失效日期", width="small"),
                "是否控制": st.column_config.SelectboxColumn("是否控制", options=CONTROL_OPTIONS, width="small"),
            },
            disabled=["母公司名称", "子公司名称", "所属板块", "业态类型", "投资分类"],
            key="ownership_editor",
        )
        if st.button("💾 保存投资占比", type="primary", use_container_width=True):
            try:
                saved = save_ownership_grid(edited_ownership)
                st.toast(f"✅ 已保存 {saved} 条投资关系")
                st.rerun()
            except Exception as ex:
                st.error(f"保存投资占比失败: {ex}")
    except Exception as e:
        st.error(f"投资占比加载失败: {e}")
    # ---------- 添加公司 ----------
    st.markdown("##### ➕ 添加新公司")
    companies = st.session_state.get("companies", pd.DataFrame())
    all_codes = companies["code"].tolist() if not companies.empty else []
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        new_code = st.text_input("公司编码（必填）", key="new_code")
    with col_a2:
        new_name = st.text_input("公司名称（必填）", key="new_name")
    with col_a3:
        new_parent = st.selectbox("上级公司（可选）", [""] + all_codes, key="new_parent")
    if st.button("➕ 添加公司", type="primary", use_container_width=True):
        if not new_code or not new_name:
            st.toast("公司编码和名称不能为空", icon="⚠️")
        else:
            session = get_session()
            try:
                session.execute(
                    text("""INSERT OR IGNORE INTO companies
                            (code, name, short_name, parent_code, level, is_consolidated, status)
                            VALUES (:c, :n, :n, :p, 1, 1, 1)"""),
                    {"c": new_code.strip(), "n": new_name.strip(),
                     "p": new_parent.strip() or None}
                )
                session.commit()
                roots = session.execute(
                    text("SELECT code FROM companies WHERE parent_code IS NULL OR parent_code = ''")
                ).fetchall()
                for r in roots:
                    rebuild_tree_path(r[0])
                session.close()
                st.session_state.companies = get_companies()
                st.toast(f"✅ 已添加 {new_name}")
                st.rerun()
            except Exception as ex:
                session.rollback()
                session.close()
                st.error(f"添加失败: {ex}")
    # ---------- 删除公司 ----------
    st.markdown("##### 🗑️ 删除公司")
    companies = st.session_state.get("companies", pd.DataFrame())
    if not companies.empty:
        del_targets = st.multiselect(
            "选择要删除的公司（将同时删除其所有子公司）",
            companies["code"].tolist(),
            format_func=lambda x: f"{x} - {companies[companies['code']==x]['name'].iloc[0] if len(companies[companies['code']==x])>0 else ''}"
        )
        if del_targets:
            st.warning(f"⚠️ 将删除 {len(del_targets)} 家公司及其所有子公司，此操作不可撤销！")
            col_dc, col_db = st.columns([1, 3])
            with col_dc:
                confirm_del = st.checkbox("确认删除", key="confirm_del_company")
            with col_db:
                if confirm_del:
                    if st.button("🗑️ 确认删除", type="primary", use_container_width=True):
                        session = get_session()
                        try:
                            all_to_delete = set()
                            for target in del_targets:
                                sub = get_subtree(target, include_self=True)
                                all_to_delete.update(sub["code"].tolist())
                            for c in all_to_delete:
                                session.execute(text("DELETE FROM company_aliases WHERE company_code = :c"), {"c": c})
                                session.execute(text("DELETE FROM dim_company WHERE company_id = :c"), {"c": c})
                                session.execute(
                                    text("DELETE FROM ownership WHERE parent_code = :c OR sub_code = :c"),
                                    {"c": c}
                                )
                                session.execute(text("DELETE FROM companies WHERE code = :c"), {"c": c})
                            session.commit()
                            roots = session.execute(
                                text("SELECT code FROM companies WHERE parent_code IS NULL OR parent_code = ''")
                            ).fetchall()
                            for r in roots:
                                rebuild_tree_path(r[0])
                            session.close()
                            st.session_state.companies = get_companies()
                            st.toast(f"✅ 已删除 {len(all_to_delete)} 家公司")
                            st.rerun()
                        except Exception as ex:
                            session.rollback()
                            session.close()
                            st.error(f"删除失败: {ex}")
    # ---------- 子树查询 ----------
    st.markdown("##### 🔍 查询子公司树")
    companies = st.session_state.get("companies", pd.DataFrame())
    if not companies.empty:
        sel_company = st.selectbox("选择母公司", [""] + companies["code"].tolist(), key="tree_sel")
        if sel_company:
            subtree = get_subtree(sel_company, include_self=True)
            if len(subtree) > 0:
                st.success(f"共 {len(subtree)} 家公司（含自身）")
                st.dataframe(subtree[["code", "name", "level", "tree_path"]], use_container_width=True, hide_index=True)


BASE_SETTINGS_READ_TABLES = {
    "company_aliases",
    "import_issue_pool",
    "base_settings_change_log",
    "name_collection_rules",
}


def _base_settings_table_exists(table_name: str) -> bool:
    if table_name not in BASE_SETTINGS_READ_TABLES:
        return False
    try:
        df = execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = :name",
            {"name": table_name},
        )
        return len(df) > 0
    except Exception:
        return False


def _base_settings_table_columns(table_name: str) -> list[str]:
    if table_name not in BASE_SETTINGS_READ_TABLES or not _base_settings_table_exists(table_name):
        return []
    try:
        df = execute_sql(f"PRAGMA table_info({table_name})")
    except Exception:
        return []
    if df.empty or "name" not in df:
        return []
    return [str(row["name"]) for _, row in df.iterrows()]


def _base_settings_read_table(table_name: str, limit: int = 200) -> pd.DataFrame:
    if table_name not in BASE_SETTINGS_READ_TABLES or not _base_settings_table_exists(table_name):
        return pd.DataFrame()
    columns = _base_settings_table_columns(table_name)
    order_col = next((col for col in ["created_at", "updated_at", "update_time", "id"] if col in columns), "")
    order_sql = f" ORDER BY {order_col} DESC" if order_col else ""
    try:
        return execute_sql(f"SELECT * FROM {table_name}{order_sql} LIMIT :limit", {"limit": int(limit)})
    except Exception:
        return pd.DataFrame()


def _base_settings_alias_rows() -> pd.DataFrame:
    if not _base_settings_table_exists("company_aliases"):
        return pd.DataFrame()
    try:
        return execute_sql(
            """
            SELECT
                a.alias AS 别名,
                CAST(a.company_code AS TEXT) AS 公司编码,
                COALESCE(c.name, '') AS 公司名称,
                COALESCE(a.source, '') AS 来源,
                CASE COALESCE(a.status, 1) WHEN 1 THEN '启用' ELSE '停用' END AS 状态,
                COALESCE(a.updated_at, a.created_at, '') AS 更新时间
            FROM company_aliases a
            LEFT JOIN companies c ON c.code = a.company_code
            ORDER BY a.alias
            LIMIT 500
            """
        )
    except Exception:
        return pd.DataFrame()


def _base_settings_alias_conflicts() -> pd.DataFrame:
    if not _base_settings_table_exists("company_aliases"):
        return pd.DataFrame()
    try:
        return execute_sql(
            """
            SELECT
                alias AS 别名,
                COUNT(DISTINCT company_code) AS 指向公司数,
                GROUP_CONCAT(DISTINCT company_code) AS 公司编码
            FROM company_aliases
            WHERE COALESCE(status, 1) = 1
              AND alias IS NOT NULL
              AND TRIM(alias) != ''
            GROUP BY alias
            HAVING COUNT(DISTINCT company_code) > 1
            ORDER BY alias
            """
        )
    except Exception:
        return pd.DataFrame()


def _shared_name_mapping_file_status() -> dict:
    path = get_shared_name_mapping_path()
    status = {
        "path": str(path),
        "exists": path.exists(),
        "record_count": None,
        "conflict_count": None,
        "generated_at": "",
        "error": "",
    }
    if not path.exists():
        return status
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        status["record_count"] = len(payload.get("records") or [])
        status["conflict_count"] = len(payload.get("conflicts") or [])
        status["generated_at"] = payload.get("generated_at") or ""
    except Exception as exc:
        status["error"] = str(exc)
    return status


def _render_shared_name_mapping_status() -> None:
    snapshot = build_shared_name_mapping_snapshot()
    stats = snapshot.get("stats", {})
    file_status = _shared_name_mapping_file_status()

    st.markdown("#### 共享映射状态")
    st.caption(
        "finance_dw 是公司名称、简称、校区名和历史别名的唯一维护入口；资金管理模块只读消费发布后的 JSON 快照。"
    )
    cols = st.columns(4)
    cols[0].metric("可发布记录", _base_metric_value(stats.get("record_count")))
    cols[1].metric("覆盖公司", _base_metric_value(stats.get("company_count")))
    cols[2].metric("冲突别名", _base_metric_value(stats.get("conflict_count")))
    cols[3].metric("未唯一匹配校区名", _base_metric_value(stats.get("unmatched_alias_count")))

    status_rows = pd.DataFrame(
        [
            ("快照路径", file_status["path"]),
            ("路径来源", f"{SHARED_NAME_MAPPING_ENV} 或默认 data/shared_name_mapping.json"),
            ("最近发布时间", file_status.get("generated_at") or "尚未发布"),
            ("已发布记录数", _base_metric_value(file_status.get("record_count")) if file_status.get("exists") else "尚未发布"),
        ],
        columns=["项目", "内容"],
    ).astype(str)
    st.dataframe(status_rows, use_container_width=True, hide_index=True, height=180)

    if file_status.get("error"):
        st.warning(f"当前快照无法读取：{file_status['error']}")
    if snapshot.get("conflicts"):
        st.error("存在启用别名指向多个公司编码，已阻止发布。")
        st.dataframe(pd.DataFrame(snapshot["conflicts"]), use_container_width=True, hide_index=True, height=180)
    if snapshot.get("unmatched_aliases"):
        with st.expander(f"未唯一匹配校区名 {len(snapshot['unmatched_aliases'])} 条", expanded=False):
            st.dataframe(pd.DataFrame(snapshot["unmatched_aliases"]), use_container_width=True, hide_index=True, height=220)

    if st.button(
        "发布 / 更新共享映射快照",
        key="base_settings_publish_shared_name_mapping",
        type="primary",
        use_container_width=True,
        disabled=bool(snapshot.get("conflicts")),
    ):
        try:
            result = publish_shared_name_mapping_snapshot()
            st.success(f"已发布 {result.get('record_count', 0)} 条共享映射：{result.get('path')}")
            st.rerun()
        except Exception as exc:
            st.error(f"共享映射发布失败：{exc}")


def _base_metric_value(value) -> str:
    if value is None:
        return "待接入"
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def _render_base_settings_home():
    st.markdown("#### 基础数据体检")
    overview = get_base_settings_overview()
    metrics = [
        ("公司数量", "company_count"),
        ("公司别名数量", "alias_count"),
        ("公司档案数量", "dimension_count"),
        ("股权关系数量", "ownership_count"),
        ("未分组公司数量", "ungrouped_company_count"),
        ("别名冲突数量", "alias_conflict_count"),
        ("未识别公司名数量", "unresolved_company_name_count"),
        ("公司档案缺失数量", "missing_dimension_count"),
        ("tree_path 异常数量", "tree_path_issue_count"),
    ]
    for start in range(0, len(metrics), 3):
        cols = st.columns(3)
        for col, (label, key) in zip(cols, metrics[start:start + 3]):
            col.metric(label, _base_metric_value(overview.get(key)))

    checks = pd.DataFrame(get_base_health_checks())
    if len(checks):
        checks_display = checks.rename(columns={
            "label": "检查项",
            "severity": "级别",
            "count": "数量",
            "status": "状态",
        })[["检查项", "级别", "数量", "状态"]]
        st.markdown("#### 数据治理检查")
        st.dataframe(checks_display, use_container_width=True, hide_index=True, height=260)
    else:
        st.info("暂无基础数据体检结果。")


def _company_hierarchy_chart_css() -> str:
    return """
    <style>
      .base-hierarchy-chart-note{
        margin:.4rem 0 .7rem;padding:.65rem .8rem;border:1px solid #bfdbfe;
        background:#eff6ff;border-radius:8px;color:#1e3a8a;font-size:.82rem;font-weight:650;
      }
      .base-hierarchy-legend{
        display:flex;flex-wrap:wrap;gap:.45rem .6rem;margin:.6rem 0 .9rem;
        color:#475569;font-size:.78rem;
      }
      .base-hierarchy-legend span{
        display:inline-flex;align-items:center;gap:.25rem;border:1px solid #dbe3ef;
        background:#fff;border-radius:999px;padding:.2rem .5rem;white-space:nowrap;
      }
      .base-company-node{
        margin:.13rem 0;padding:.58rem .68rem;border:1px solid #d8e2ef;border-radius:8px;
        background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.04);
      }
      .base-company-node.root{background:#0b2342;border-color:#0b2342;color:#fff;}
      .base-company-node.inactive{background:#f8fafc;color:#64748b;border-style:dashed;}
      .base-company-node.issue{border-color:#f59e0b;background:#fffbeb;}
      .base-company-node-title{font-weight:800;font-size:.9rem;line-height:1.25;}
      .base-company-node-code{margin-top:.18rem;color:#64748b;font-size:.74rem;font-weight:700;}
      .base-company-node.root .base-company-node-code{color:#cbd5e1;}
      .base-company-node-tags{margin-top:.36rem;display:flex;gap:.28rem;flex-wrap:wrap;}
      .base-company-node-tag{
        display:inline-flex;align-items:center;height:20px;padding:0 .42rem;border-radius:999px;
        background:#eef6ff;color:#1d4ed8;border:1px solid #bfdbfe;font-size:.68rem;font-weight:800;
      }
      .base-company-node-tag.off{background:#f1f5f9;color:#64748b;border-color:#cbd5e1;}
      .base-company-node-tag.warn{background:#fff7ed;color:#c2410c;border-color:#fed7aa;}
      .base-company-node-wrap{border-left:1px solid #e2e8f0;padding-left:.55rem;}
    </style>
    """


def render_company_node_card(
    node: dict,
    *,
    depth: int,
    show_code: bool,
    show_consolidated: bool,
) -> str:
    classes = ["base-company-node"]
    if node.get("is_root"):
        classes.append("root")
    if node.get("status") == 0:
        classes.append("inactive")
    if node.get("issue_flags"):
        classes.append("issue")
    tags = []
    if node.get("is_root"):
        tags.append('<span class="base-company-node-tag">ROOT 节点</span>')
    if node.get("status") == 0:
        tags.append('<span class="base-company-node-tag off">停用</span>')
    if show_consolidated and node.get("is_consolidated") == 1 and not node.get("is_root"):
        tags.append('<span class="base-company-node-tag">合并</span>')
    if node.get("issue_flags"):
        tags.append(f'<span class="base-company-node-tag warn">{_html(node.get("issue_label") or "异常")}</span>')
    code_html = f'<div class="base-company-node-code">{_html(node.get("code"))}</div>' if show_code else ""
    return f"""
    <div class="base-company-node-wrap" style="margin-left:{max(depth, 0) * 1.25}rem;">
      <div class="{' '.join(classes)}">
        <div class="base-company-node-title">{_html(node.get("display_name") or node.get("name") or node.get("code"))}</div>
        {code_html}
        <div class="base-company-node-tags">{''.join(tags)}</div>
      </div>
    </div>
    """


def render_company_node_detail_panel(node: dict | None, issues: list[dict]) -> None:
    st.markdown("##### 节点信息")
    if not node:
        st.info("选择一个节点查看公司信息。")
        return
    related_issues = [item for item in issues if item.get("company_code") == node.get("code")]
    detail_rows = [
        ("公司名称", node.get("name")),
        ("公司简称", node.get("short_name")),
        ("公司编码", node.get("code")),
        ("上级公司", node.get("parent_code") or "ROOT"),
        ("公司层级", node.get("level")),
        ("合并范围", node.get("consolidated_label")),
        ("公司状态", node.get("status_label")),
        ("是否末级", "是" if int(node.get("is_leaf") or 0) == 1 else "否"),
        ("树路径", node.get("tree_path")),
        ("备注", "；".join(item.get("detail", "") for item in related_issues) if related_issues else "无"),
    ]
    st.dataframe(
        pd.DataFrame(detail_rows, columns=["字段", "内容"]),
        use_container_width=True,
        hide_index=True,
        height=360,
    )


def _company_hierarchy_status_visible(node: dict, status_filter: str) -> bool:
    if node.get("is_root") or status_filter == "全部":
        return True
    if status_filter == "启用":
        return int(node.get("status") or 0) != 0
    if status_filter == "停用":
        return int(node.get("status") or 0) == 0
    return True


def _render_company_hierarchy_node(
    code: str,
    *,
    depth: int,
    graph_data: dict,
    expanded_codes: set[str],
    selected_key: str,
    expanded_key: str,
    depth_limit: int | None,
    status_filter: str,
    show_code: bool,
    show_consolidated: bool,
    visited: set[str],
) -> None:
    if code in visited:
        return
    if depth_limit is not None and depth > depth_limit:
        return
    visited.add(code)
    nodes = graph_data.get("nodes", {})
    children_map = graph_data.get("children_map", {})
    node = nodes.get(code)
    if not node:
        return

    children = children_map.get(code, [])
    has_children = bool(children)
    visible = _company_hierarchy_status_visible(node, status_filter)
    if visible:
        toggle_col, card_col, action_col = st.columns([0.5, 7.5, 1.1])
        with toggle_col:
            if has_children:
                toggle_label = "-" if code in expanded_codes else "+"
                if st.button(toggle_label, key=f"base_hierarchy_toggle_{code}", help="+ 可展开，- 已展开"):
                    current = set(st.session_state.get(expanded_key, []))
                    if code in current:
                        current.remove(code)
                    else:
                        current.add(code)
                    st.session_state[expanded_key] = sorted(current)
                    st.rerun()
            else:
                st.markdown("&nbsp;", unsafe_allow_html=True)
        with card_col:
            st.markdown(
                render_company_node_card(
                    node,
                    depth=depth,
                    show_code=show_code,
                    show_consolidated=show_consolidated,
                ),
                unsafe_allow_html=True,
            )
        with action_col:
            if st.button("查看", key=f"base_hierarchy_select_{code}", use_container_width=True):
                st.session_state[selected_key] = code
                st.rerun()

    if code in expanded_codes:
        for child_code in children:
            _render_company_hierarchy_node(
                child_code,
                depth=depth + 1,
                graph_data=graph_data,
                expanded_codes=expanded_codes,
                selected_key=selected_key,
                expanded_key=expanded_key,
                depth_limit=depth_limit,
                status_filter=status_filter,
                show_code=show_code,
                show_consolidated=show_consolidated,
                visited=visited,
            )


def render_company_hierarchy_structure_chart() -> None:
    st.markdown(_company_hierarchy_chart_css(), unsafe_allow_html=True)
    st.markdown(
        """
        <div class="base-hierarchy-chart-note">
        结构图展示的是 companies.parent_code 形成的公司上下级关系。业务模块归属请到“公司档案”维护，调整业务模块不要修改公司上级。
        </div>
        """,
        unsafe_allow_html=True,
    )
    graph_data = build_company_hierarchy_graph_data()
    root_code = graph_data.get("root_code", COMPANY_HIERARCHY_ROOT_CODE)
    nodes = graph_data.get("nodes", {})
    children_map = graph_data.get("children_map", {})
    issues = graph_data.get("issues", [])

    expanded_key = "base_company_hierarchy_expanded"
    selected_key = "base_company_hierarchy_selected"
    if expanded_key not in st.session_state:
        st.session_state[expanded_key] = get_default_expanded_company_codes(graph_data=graph_data)
    if selected_key not in st.session_state:
        st.session_state[selected_key] = root_code

    ctrl_cols = st.columns([1.05, 1.05, 1.1, 1.2, 0.9, 0.9, 0.9])
    with ctrl_cols[0]:
        depth_option = st.selectbox("显示层级", ["全部", "1级", "2级", "3级", "4级"], key="base_hierarchy_depth")
    with ctrl_cols[1]:
        status_filter = st.selectbox("公司状态", ["全部", "启用", "停用"], key="base_hierarchy_status")
    with ctrl_cols[2]:
        show_code = st.checkbox("显示公司编码", value=True, key="base_hierarchy_show_code")
    with ctrl_cols[3]:
        show_consolidated = st.checkbox("显示合并标记", value=True, key="base_hierarchy_show_consolidated")
    with ctrl_cols[4]:
        if st.button("全部展开", key="base_hierarchy_expand_all", use_container_width=True):
            st.session_state[expanded_key] = sorted([code for code, children in children_map.items() if children])
            st.rerun()
    with ctrl_cols[5]:
        if st.button("全部收起", key="base_hierarchy_collapse_all", use_container_width=True):
            st.session_state[expanded_key] = [root_code]
            st.rerun()
    with ctrl_cols[6]:
        if st.button("刷新", key="base_hierarchy_refresh", use_container_width=True):
            st.session_state[expanded_key] = get_default_expanded_company_codes(graph_data=graph_data)
            st.session_state[selected_key] = root_code
            st.rerun()

    st.markdown(
        """
        <div class="base-hierarchy-legend">
          <span>ROOT 节点</span><span>启用公司</span><span>停用公司</span><span>合并范围公司</span>
          <span>异常节点</span><span>+ 可展开</span><span>- 已展开</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if issues:
        with st.expander(f"层级异常 {len(issues)} 条", expanded=False):
            st.dataframe(pd.DataFrame(issues), use_container_width=True, hide_index=True, height=220)

    depth_limit = None if depth_option == "全部" else int(depth_option.replace("级", ""))
    expanded_codes = set(st.session_state.get(expanded_key, [root_code]))
    selected_code = st.session_state.get(selected_key, root_code)
    left_col, right_col = st.columns([3.2, 1.2])
    with left_col:
        if not children_map.get(root_code):
            st.info("暂无公司层级数据。")
        else:
            _render_company_hierarchy_node(
                root_code,
                depth=0,
                graph_data=graph_data,
                expanded_codes=expanded_codes,
                selected_key=selected_key,
                expanded_key=expanded_key,
                depth_limit=depth_limit,
                status_filter=status_filter,
                show_code=show_code,
                show_consolidated=show_consolidated,
                visited=set(),
            )
    with right_col:
        render_company_node_detail_panel(nodes.get(selected_code), issues)


def _render_base_settings_org():
    st.info("组织架构用于维护公司上下级、组织树和合并范围；不要用它调整经营分析业务模块。")
    tabs = st.tabs(["公司清单", "公司树", "结构图", "合并范围", "股权控制关系"])
    with tabs[0]:
        try:
            tree = get_company_tree()
            if len(tree):
                st.dataframe(tree, use_container_width=True, hide_index=True, height=520)
            else:
                st.info("暂无公司清单。")
        except Exception as exc:
            st.error(f"公司清单加载失败: {exc}")
    with tabs[1]:
        render_company_hierarchy()
    with tabs[2]:
        render_company_hierarchy_structure_chart()
    with tabs[3]:
        try:
            structure_df = get_company_structure_view()
            if len(structure_df):
                st.dataframe(structure_df, use_container_width=True, hide_index=True, height=520)
            else:
                st.info("暂无合并范围数据。")
        except Exception as exc:
            st.error(f"合并范围加载失败: {exc}")
    with tabs[4]:
        try:
            ownership_df = get_ownership_grid()
            if len(ownership_df):
                ownership_display = ownership_df.rename(columns={
                    "parent_code": "母公司编码",
                    "parent_name": "母公司名称",
                    "sub_code": "子公司编码",
                    "sub_name": "子公司名称",
                    "business_group": "所属板块",
                    "business_type": "业态类型",
                    "ownership_pct": "投资占比(%)",
                    "investment_category": "投资分类",
                    "effective_date": "生效日期",
                    "expiration_date": "失效日期",
                    "is_control": "是否控制",
                })
                visible_cols = [
                    "母公司编码", "母公司名称", "子公司编码", "子公司名称",
                    "所属板块", "业态类型", "投资占比(%)", "投资分类",
                    "生效日期", "失效日期", "是否控制",
                ]
                visible_cols = [col for col in visible_cols if col in ownership_display.columns]
                st.dataframe(
                    ownership_display[visible_cols],
                    use_container_width=True,
                    hide_index=True,
                    height=520,
                    column_config={
                        "母公司编码": st.column_config.TextColumn("母公司编码", width="small"),
                        "母公司名称": st.column_config.TextColumn("母公司名称", width="medium"),
                        "子公司编码": st.column_config.TextColumn("子公司编码", width="small"),
                        "子公司名称": st.column_config.TextColumn("子公司名称", width="medium"),
                        "所属板块": st.column_config.TextColumn("所属板块", width="small"),
                        "业态类型": st.column_config.TextColumn("业态类型", width="small"),
                        "投资占比(%)": st.column_config.NumberColumn("投资占比(%)", format="%.2f", width="small"),
                        "投资分类": st.column_config.TextColumn("投资分类", width="small"),
                        "生效日期": st.column_config.TextColumn("生效日期", width="small"),
                        "失效日期": st.column_config.TextColumn("失效日期", width="small"),
                        "是否控制": st.column_config.TextColumn("是否控制", width="small"),
                    },
                )
            else:
                st.info("暂无股权控制关系。")
        except Exception as exc:
            st.error(f"股权控制关系加载失败: {exc}")


def _render_base_settings_company_profile():
    st.info("组织架构用于维护公司上下级和合并范围；公司档案中的业务模块用于经营分析口径；调整业务模块不要修改公司上级。")
    try:
        dim_df = get_company_dimensions()
    except Exception as exc:
        st.error(f"公司档案加载失败: {exc}")
        return

    if len(dim_df) == 0:
        st.info("暂无公司档案数据。")
        return

    dim_edit = dim_df.rename(columns={
        "company_id": "公司编码",
        "company_name": "公司名称",
        "business_group": "所属板块",
        "business_type": "业态类型",
        "region": "所属区域",
        "is_operational": "运营主体",
        "parent_code": "上级编码",
        "level": "层级",
    })
    visible_cols = ["公司编码", "公司名称", "所属板块", "业态类型", "所属区域", "运营主体", "上级编码", "层级"]
    edited_dim = st.data_editor(
        dim_edit[visible_cols],
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "公司编码": st.column_config.TextColumn("公司编码", width="small", disabled=True),
            "公司名称": st.column_config.TextColumn("公司名称", width="medium", disabled=True),
            "所属板块": st.column_config.SelectboxColumn("所属板块", options=BUSINESS_GROUP_OPTIONS, width="small"),
            "业态类型": st.column_config.SelectboxColumn("业态类型", options=BUSINESS_TYPE_OPTIONS, width="small"),
            "所属区域": st.column_config.SelectboxColumn("所属区域", options=REGION_OPTIONS, width="small"),
            "运营主体": st.column_config.SelectboxColumn("运营主体", options=OPERATIONAL_OPTIONS, width="small"),
            "上级编码": st.column_config.TextColumn("上级编码", width="small", disabled=True),
            "层级": st.column_config.NumberColumn("层级", width="small", disabled=True),
        },
        disabled=["公司编码", "公司名称", "上级编码", "层级"],
        key="base_settings_company_dimension_editor",
    )
    if st.button("保存公司档案", type="primary", use_container_width=True):
        try:
            saved = save_company_dimensions(edited_dim)
            st.toast(f"已保存 {saved} 家公司档案")
            st.rerun()
        except Exception as exc:
            st.error(f"保存公司档案失败: {exc}")


def _render_base_settings_naming():
    st.info("名称口径用于维护公司别名和文件名识别。模糊匹配只能作为建议，不能自动写入正式别名。")
    probe = st.text_input("公司名 / 文件名识别预检", key="base_settings_identity_probe")
    if probe.strip():
        result = resolve_company_identity(probe.strip(), mode="fuzzy")
        if result.get("ok"):
            st.success(f"已精确识别：{result['company_code']} - {result['company_name']}")
        elif result.get("suggestions"):
            st.warning("未精确命中，以下仅为建议，需人工确认后才能维护别名。")
            st.dataframe(pd.DataFrame(result["suggestions"]), use_container_width=True, hide_index=True)
        else:
            st.info("未识别到候选公司。")

    _render_shared_name_mapping_status()

    alias_df = _base_settings_alias_rows()
    st.markdown("#### 公司别名")
    if len(alias_df):
        st.dataframe(alias_df, use_container_width=True, hide_index=True, height=320)
        st.download_button(
            "导出别名清单",
            alias_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="公司别名清单.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("暂无公司别名数据。")

    conflicts = _base_settings_alias_conflicts()
    st.markdown("#### 冲突别名")
    if len(conflicts):
        st.error(f"发现 {len(conflicts)} 个启用别名指向多个公司。")
        st.dataframe(conflicts, use_container_width=True, hide_index=True)
    else:
        st.success("当前没有发现启用别名冲突。")

    st.markdown("#### 预算校区名称映射")
    st.caption("用于把预算表中的校区名称对应到系统实际经营单位/校区名称；该口径供全面预算、课消、方案结果等模块复用。")
    budget_mapping_df = get_budget_campus_mapping_records()
    if len(budget_mapping_df):
        st.table(budget_mapping_df)
    else:
        st.info("暂无预算校区名称映射。")

    st.markdown("#### 未识别公司名")
    issue_df = _base_settings_read_table("import_issue_pool", limit=100)
    if len(issue_df):
        st.dataframe(issue_df, use_container_width=True, hide_index=True, height=260)
    else:
        st.info("导入问题池未接入或暂无未识别公司名记录。")

    with st.expander("别名导入入口", expanded=False):
        st.caption("正式写入 company_aliases 前必须人工确认。本轮只保留入口，不做模糊匹配自动入库。")


def _render_base_settings_collection_rules():
    st.info("归集规则第一版只展示现有口径和维护入口，不修改经营汇总计算逻辑。")
    standard_items = [row.get("费用科目") for row in build_empty_operating_summary_rows()]
    item_df = pd.DataFrame({"经营汇总标准项目": standard_items})
    st.markdown("#### 经营项目归集")
    st.dataframe(item_df, use_container_width=True, hide_index=True, height=260)

    rules_df = _base_settings_read_table("name_collection_rules", limit=200)
    st.markdown("#### 名称归集规则表")
    if len(rules_df):
        st.dataframe(rules_df, use_container_width=True, hide_index=True, height=260)
    else:
        st.info("name_collection_rules 尚未接入或暂无数据；后续可在这里集中维护业务模块历史名称、经营项目、科目指标归集。")


def _render_base_settings_import_issues():
    st.markdown("#### 导入问题池")
    issue_df = _base_settings_read_table("import_issue_pool", limit=300)
    if len(issue_df):
        st.dataframe(issue_df, use_container_width=True, hide_index=True, height=520)
    else:
        st.info("导入预检中发现的未识别公司、未识别项目、未识别科目后续将在这里集中处理。当前表结构未接入或暂无数据。")


def _render_base_settings_change_log():
    st.markdown("#### 变更记录")
    log_df = _base_settings_read_table("base_settings_change_log", limit=300)
    if len(log_df):
        st.dataframe(log_df, use_container_width=True, hide_index=True, height=520)
    else:
        st.info("后续用于记录公司档案、名称口径、归集规则等基础设置变更。当前表结构未接入或暂无数据。")


def render_base_settings():
    st.markdown('<div class="page-header">⚙️ 基础设置</div>', unsafe_allow_html=True)
    tab_labels = ["首页", "组织架构", "公司档案", "名称口径", "归集规则", "导入问题池", "变更记录"]
    active_tab = st.session_state.get("base_settings_active_tab", "首页")
    if active_tab not in tab_labels:
        active_tab = "首页"
    tabs = st.tabs(tab_labels, default=active_tab, key=f"base_settings_tabs_{active_tab}")
    with tabs[0]:
        _render_base_settings_home()
    with tabs[1]:
        _render_base_settings_org()
    with tabs[2]:
        _render_base_settings_company_profile()
    with tabs[3]:
        _render_base_settings_naming()
    with tabs[4]:
        _render_base_settings_collection_rules()
    with tabs[5]:
        _render_base_settings_import_issues()
    with tabs[6]:
        _render_base_settings_change_log()


def render_consolidated():
    st.markdown('<div class="page-header">🏢 合并报表</div>', unsafe_allow_html=True)
    report_type = st.selectbox("报表类型", ["资产负债表", "损益表"])
    years, months = _get_year_month_options()
    col_p1, col_p2 = st.columns([1, 1])
    with col_p1: sel_year = st.selectbox("年份", [""] + years if years else ["2026"], key="con_y")
    with col_p2: sel_month = st.selectbox("月份", [""] + months if months else ["03"], key="con_m")
    sel_period = (sel_year + sel_month) if sel_year and sel_month else ""

    # 层级汇总模式
    use_hierarchy = st.checkbox("按公司层级自动汇总（选中母公司自动包含所有子孙公司）", value=False, key="use_hier")
    companies = st.session_state.get("companies", pd.DataFrame())

    if use_hierarchy:
        # 层级模式：选母公司
        company_list = companies["code"].tolist() if not companies.empty else []
        sel_parent = st.selectbox("选择母公司（自动汇总其所有子孙公司）", [""] + company_list, key="hier_parent")
        sel_companies = []
    else:
        # 手动模式：多选公司
        if not companies.empty:
            opts = companies.set_index("code")["name"].to_dict()
            sel_companies = st.multiselect("选择要合并的公司", options=list(opts.keys()), format_func=lambda x: f"{x} - {opts.get(x, '')}")
        else:
            sel_companies = st.multiselect("选择要合并的公司", [])
        sel_parent = None
    if st.button("生成合并报表", type="primary", icon=":material/account_tree:", use_container_width=True):
        if not sel_period:
            st.toast("请选择期间", icon="⚠️"); return
        if not sel_companies and not sel_parent:
            st.toast("请选择公司", icon="⚠️"); return

        with st.spinner("⏳ 生成中..."):
            kwargs = {"period": sel_period}
            if use_hierarchy and sel_parent:
                kwargs["parent_code"] = sel_parent
            else:
                kwargs["company_list"] = sel_companies

            df = get_consolidated_balance_sheet(**kwargs) if report_type == "资产负债表" else get_consolidated_income_statement(**kwargs)
            if len(df) > 0:
                st.toast(f"✅ 生成成功！共 {len(df)} 条记录")
                df = _cn_cols(df, {"account_code": "科目编码", "account_name": "科目名称", "ending_balance": "期末余额", "direction": "方向", "category": "类别", "total_amount": "总金额", "opening_balance": "期初余额", "debit_amount": "借方发生额", "credit_amount": "贷方发生额"})
                config = {}
                for c in df.select_dtypes(include=['float64', 'int64']).columns:
                    config[c] = st.column_config.NumberColumn(c, format="%,.2f")
                st.dataframe(df, use_container_width=True, hide_index=True, height=600, column_config=config)
            else:
                st.toast("未生成数据，请检查对应期间是否有数据", icon="⚠️")

def render_multi_period():
    st.markdown('<div class="page-header">📊 多期对比分析</div>', unsafe_allow_html=True)
    years, months = _get_year_month_options()
    companies = st.session_state.get("companies", pd.DataFrame())
    company_list = companies["code"].tolist() if not companies.empty else []
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1: sel_company = st.selectbox("选择公司", company_list) if company_list else st.text_input("公司编码")
    with col2: sel_sy = st.selectbox("起始年", [""] + years if years else ["2026"], key="msy")
    with col3: sel_sm = st.selectbox("起始月", [""] + months if months else ["01"], key="msm")
    with col4: report_type = st.selectbox("数据类型", ["科目余额表", "损益明细表"])
    start_period = (sel_sy + sel_sm) if sel_sy and sel_sm else "202601"
    col_e1, col_e2 = st.columns([1, 1])
    with col_e1: sel_ey = st.selectbox("结束年", [""] + years if years else ["2026"], key="mey")
    with col_e2: sel_em = st.selectbox("结束月", [""] + months if months else ["12"], key="mem")
    end_period = (sel_ey + sel_em) if sel_ey and sel_em else "202612"
    if st.button("生成对比", type="primary", icon=":material/bar_chart:", use_container_width=True):
        with st.spinner("⏳ 查询中..."):
            type_map = {"科目余额表": "account_balance", "损益明细表": "pl_detail"}
            df = get_multi_period_summary(sel_company, start_period, end_period, type_map[report_type])
            if len(df) > 0:
                st.toast(f"✅ 查询成功！共 {len(df)} 条记录")
                df = _cn_cols(df, {"account_code": "科目编码", "account_name": "科目名称", "period": "期间", "opening_balance": "期初余额", "debit_amount": "借方发生额", "credit_amount": "贷方发生额", "ending_balance": "期末余额", "category": "类别", "item_code": "项目编码", "amount": "金额"})
                config = {}
                for c in df.select_dtypes(include=['float64', 'int64']).columns:
                    config[c] = st.column_config.NumberColumn(c, format="%,.2f")
                st.dataframe(df, use_container_width=True, hide_index=True, height=500, column_config=config)
            else:
                st.toast("未查询到数据", icon="⚠️")


def _render_account_mapping_admin():
    ensure_account_standardization_schema()
    periods = get_dashboard_periods()
    companies = st.session_state.get("companies", pd.DataFrame())
    if companies is None or companies.empty:
        try:
            companies = get_companies()
        except Exception:
            companies = pd.DataFrame()
    company_options = [""] + companies["code"].astype(str).tolist() if not companies.empty else [""]
    company_name_map = companies.set_index("code")["name"].to_dict() if not companies.empty else {}

    st.markdown("##### 科目映射数据质量")
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        period = st.selectbox("检查期间", [""] + periods, index=1 if periods else 0, key="account_mapping_period")
    with filter_col2:
        company_code = st.selectbox(
            "公司范围",
            company_options,
            format_func=lambda code: "全部公司" if code == "" else f"{code} - {company_name_map.get(code, code)}",
            key="account_mapping_company",
        )

    coverage = get_mapping_coverage(period or None, company_code or None)
    _render_bi_kpi_grid(
        [
            {"label": "原始科目数", "value": coverage["total_accounts"], "type": "number", "delta": None},
            {"label": "已映射科目", "value": coverage["mapped_accounts"], "type": "number", "delta": coverage["coverage_rate"]},
            {"label": "未映射科目", "value": coverage["unmapped_accounts"], "type": "number", "delta": None},
            {"label": "覆盖率", "value": coverage["coverage_rate"], "type": "percent", "delta": None},
        ]
    )
    st.caption(f"覆盖状态：{coverage['level']}。覆盖率 100% 为正常，95%-100% 关注，低于 95% 待处理。")

    tab_standard, tab_mapping, tab_unmapped = st.tabs(["标准科目", "映射维护", "未映射检查"])
    with tab_standard:
        standard_df = get_standard_accounts()
        st.caption("维护统一标准科目体系。新增行时至少填写标准科目编码、标准科目名称、科目类别。")
        standard_edit = st.data_editor(
            standard_df if len(standard_df) else pd.DataFrame(
                columns=["标准科目编码", "标准科目名称", "科目类别", "余额方向", "层级", "上级科目编码", "是否末级", "状态", "排序"]
            ),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            height=360,
            column_config={
                "科目类别": st.column_config.SelectboxColumn("科目类别", options=["资产", "负债", "权益", "成本", "损益", "未分类"]),
                "余额方向": st.column_config.SelectboxColumn("余额方向", options=["借", "贷"]),
                "层级": st.column_config.NumberColumn("层级", min_value=1, step=1, format="%d"),
                "是否末级": st.column_config.NumberColumn("是否末级", min_value=0, max_value=1, step=1, format="%d"),
                "状态": st.column_config.NumberColumn("状态", min_value=0, max_value=1, step=1, format="%d"),
                "排序": st.column_config.NumberColumn("排序", min_value=0, step=1, format="%d"),
            },
            key="standard_account_editor",
        )
        if st.button("保存标准科目", type="primary", use_container_width=True):
            saved = 0
            errors = []
            for _, row in standard_edit.iterrows():
                if not str(row.get("标准科目编码", "")).strip():
                    continue
                try:
                    upsert_standard_account(row.to_dict())
                    saved += 1
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                st.error("；".join(errors[:3]))
            st.toast(f"已保存 {saved} 条标准科目")
            st.rerun()

    with tab_mapping:
        mapping_company = company_code or None
        mapping_df = get_account_mappings(mapping_company)
        st.caption("公司编码可填具体公司，也可填 ALL 作为全局映射。原始科目编码 + 公司编码唯一。")
        mapping_edit = st.data_editor(
            mapping_df if len(mapping_df) else pd.DataFrame(
                columns=["公司编码", "公司名称", "原始科目编码", "原始科目名称", "标准科目编码", "标准科目名称", "科目类别", "映射类型", "生效期间", "失效期间", "创建时间"]
            ),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            height=420,
            column_config={
                "公司编码": st.column_config.TextColumn("公司编码", help="具体公司编码或 ALL"),
                "公司名称": st.column_config.TextColumn("公司名称", disabled=True),
                "原始科目编码": st.column_config.TextColumn("原始科目编码", required=True),
                "标准科目编码": st.column_config.TextColumn("标准科目编码", required=True),
                "科目类别": st.column_config.TextColumn("科目类别", disabled=True),
                "映射类型": st.column_config.SelectboxColumn("映射类型", options=["精确映射", "范围映射", "手工确认"]),
                "创建时间": st.column_config.TextColumn("创建时间", disabled=True),
            },
            disabled=["公司名称", "科目类别", "创建时间"],
            key="account_mapping_editor",
        )
        if st.button("保存映射关系", type="primary", use_container_width=True):
            saved = 0
            errors = []
            for _, row in mapping_edit.iterrows():
                if not str(row.get("原始科目编码", "")).strip() and not str(row.get("标准科目编码", "")).strip():
                    continue
                try:
                    upsert_account_mapping(row.to_dict())
                    saved += 1
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                st.error("；".join(errors[:3]))
            st.toast(f"已保存 {saved} 条映射关系")
            st.rerun()

    with tab_unmapped:
        suggestions_df = suggest_account_mappings(period or None, company_code or None)
        if len(suggestions_df) == 0:
            st.success("当前筛选范围没有未映射科目。")
        else:
            st.caption("建议列仅作初筛，保存前请人工确认标准科目编码。")
            st.dataframe(suggestions_df, use_container_width=True, hide_index=True, height=420)
            quick_df = suggestions_df[
                suggestions_df["建议标准科目编码"].astype(str).str.strip() != ""
            ].copy()
            if len(quick_df):
                if st.button("保存有建议的映射", use_container_width=True):
                    saved = 0
                    for _, row in quick_df.iterrows():
                        upsert_account_mapping(
                            {
                                "公司编码": row["公司编码"],
                                "原始科目编码": row["原始科目编码"],
                                "原始科目名称": row["原始科目名称"],
                                "标准科目编码": row["建议标准科目编码"],
                                "标准科目名称": row["建议标准科目名称"],
                                "映射类型": "手工确认",
                            }
                        )
                        saved += 1
                    st.toast(f"已保存 {saved} 条建议映射")
                    st.rerun()


def render_admin():
    st.markdown('<div class="page-header">⚙️ 系统管理</div>', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["📊 数据库状态", "🏢 公司管理", "科目映射", "ℹ️ 关于"])
    with tab1:
        st.markdown("##### 各表记录数")
        tables = [("companies", "公司信息"), ("account_balance", "科目余额"), ("pl_detail", "损益明细"), ("revenue_volume", "收入人次"), ("non_subject_allocation", "非学科费用分配"), ("mgmt_dept_income_cost", "管理中心部门"), ("non_subject_teaching_fee", "非学科课酬"), ("import_logs", "导入日志")]
        stats = []
        for tbl, lbl in tables:
            try:
                cnt = execute_sql(f"SELECT COUNT(*) as cnt FROM {tbl}").iloc[0, 0]
            except Exception:
                cnt = 0
            stats.append({"表名": lbl, "记录数": cnt})
        st.dataframe(pd.DataFrame(stats), use_container_width=True, hide_index=True)
        # 清除数据
        st.markdown("---")
        st.markdown("##### 🗑️ 清除数据")
        clear_target = st.selectbox("选择要清除的表", ["", "account_balance（科目余额）", "pl_detail（损益明细）", "revenue_volume（收入人次）", "non_subject_allocation（非学科费用分配）", "mgmt_dept_income_cost（管理中心部门）", "non_subject_teaching_fee（非学科课酬）", "import_logs（导入日志）", "companies（公司信息）", "全部数据"], key="clear_select")
        table_map = {"account_balance（科目余额）": "account_balance", "pl_detail（损益明细）": "pl_detail", "revenue_volume（收入人次）": "revenue_volume", "non_subject_allocation（非学科费用分配）": "non_subject_allocation", "mgmt_dept_income_cost（管理中心部门）": "mgmt_dept_income_cost", "non_subject_teaching_fee（非学科课酬）": "non_subject_teaching_fee", "import_logs（导入日志）": "import_logs", "companies（公司信息）": "companies"}
        col_cf1, col_cf2 = st.columns([1, 3])
        with col_cf1:
            confirm_clear = st.checkbox("确认清除", key="confirm_clear")
        with col_cf2:
            if confirm_clear and clear_target:
                if clear_target == "全部数据":
                    if st.button("⚠️ 确认清除全部数据", type="primary", use_container_width=True):
                        session = get_session()
                        try:
                            for tbl in list(table_map.values()) + ["non_subject_mgmt_dept_income_cost"]:
                                session.execute(text(f"DELETE FROM {tbl}"))
                            session.commit()
                            init_database()
                            st.session_state.companies = get_companies()
                            st.success("✅ 全部数据已清除")
                        except Exception as ex:
                            session.rollback()
                            st.error(f"清除失败: {ex}")
                        finally:
                            session.close()
                        st.rerun()
                else:
                    tbl_name = table_map.get(clear_target)
                    if tbl_name and st.button(f"确认清除", type="primary", use_container_width=True):
                        session = get_session()
                        try:
                            session.execute(text(f"DELETE FROM {tbl_name}"))
                            session.commit()
                            if tbl_name == "companies":
                                st.session_state.companies = get_companies()
                            st.success(f"✅ {clear_target} 数据已清除")
                        except Exception as ex:
                            session.rollback()
                            st.error(f"清除失败: {ex}")
                        finally:
                            session.close()
                        st.rerun()

    with tab2:
        try:
            companies_df = get_companies()
            if len(companies_df) > 0:
                st.dataframe(companies_df, use_container_width=True, hide_index=True)
            else:
                st.info("暂无公司信息")
        except Exception:
            pass
    with tab3:
        _render_account_mapping_admin()
    with tab4:
        st.markdown("""<div class="card"><h4>📊 财务数据仓库系统</h4><p><strong>版本</strong>: 1.0.0</p><p><strong>技术栈</strong>: Python 3.10+ · SQLite · Pandas · Streamlit · OpenPyXL</p><hr><p style="color:#999;font-size:0.85rem;">数据库: <code>finance_dw/data/finance_dw.db</code></p></div>""", unsafe_allow_html=True)

def render_footer():
    st.markdown('<div class="app-footer">© 2026 <strong>财务数据仓库系统</strong> · Built with Streamlit &amp; DeepSeek V4</div>', unsafe_allow_html=True)

def main():
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    init_app()
    st.markdown(_render_ui_font_size_css(_current_ui_font_size_mode()), unsafe_allow_html=True)
    choice = render_sidebar()
    page_map = {
        "首页": render_home,
        "数据导入": render_import,
        "科目余额表": render_account_balance,
        "资产负债表": render_balance_sheet,
        "损益表": render_income_statement,
        "现金流量表": render_cashflow,
        "核算记录": render_accounting_records,
        "明细表查询": render_detail_tables,
        "多维图片简报": render_multi_picture_brief,
        "贡献式利润表": render_contribution_profit_statement,
        "多维损益表": render_multi_income_statement,
        "多维经营汇总表": render_multi_operating_summary,
        "利润表总览驾驶舱": render_profit_dashboard,
        "利润表明细（原表）": render_profit_original_table,
        "费用科目分析": render_expense_subject_analysis,
        "资金预警": render_funds_warning,
        "全面预算": render_budget_dashboard,
        "盈亏平衡测算": render_break_even_calculator,
        "合并报表": render_consolidated,
        "多期对比": render_multi_period,
        "基础设置": render_base_settings,
        "base_settings.overview": render_base_settings,
        "base_settings.organization": render_base_settings,
        "base_settings.company_profile": render_base_settings,
        "base_settings.name_standard": render_base_settings,
        "base_settings.collection_rules": render_base_settings,
        "base_settings.import_issues": render_base_settings,
        "base_settings.change_log": render_base_settings,
        "公司层级": render_company_hierarchy,
        "系统管理": render_admin,
    }
    page_slot = st.empty()
    with page_slot.container():
        page_map.get(choice, render_home)()
        render_footer()
    st.session_state["_last_rendered_page"] = choice

if __name__ == "__main__":
    main()
