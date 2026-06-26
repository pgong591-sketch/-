"""
财务数据仓库 - Streamlit Web 界面 (精美版)
提供上传、查询、导出等功能的可视化界面。
启动方式：streamlit run app.py
"""

import os, sys, tempfile, io, zipfile
from pathlib import Path
from html import escape
from math import ceil
from numbers import Number
from xml.sax.saxutils import escape as xml_escape
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.db_connection import init_database, execute_sql, get_session
from sqlalchemy import text

from src.reports import (
    import_excel_to_db, precheck_import, get_companies, get_company, get_account_balance,
    get_balance_sheet, get_income_statement, get_cashflow,
    get_consolidated_balance_sheet, get_consolidated_income_statement,
    get_multi_period_summary, get_pl_detail, get_revenue_volume,
    get_non_subject_allocation, get_mgmt_dept_income_cost, get_non_subject_teaching_fee,
)
from src.models import REPORT_TYPES_CN
from src.excel_exporter import export_to_excel, export_balance_sheet, export_income_statement, export_cashflow, export_account_balance
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
from src.dashboard_metrics import COST_ITEMS, INCOME_ITEM, NET_PROFIT_ITEM, get_dashboard_periods, get_home_dashboard
from src.multidim_reports import get_multidim_income_statement, get_operating_summary
from src.template_workbook import TemplateWorkbookError, load_template_sheet, read_template_bytes
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
    get_base_health_checks,
    get_base_settings_overview,
    resolve_company_identity,
)

try:
    import plotly.express as px
except Exception:
    px = None

st.set_page_config(page_title="财务数据仓库", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

PAGE_CSS = """
<style>
    :root {
        --app-bg: #f4f6fb;
        --surface: #ffffff;
        --surface-soft: #f8fbff;
        --text: #122033;
        --muted: #64748b;
        --border: #cfd9e8;
        --border-soft: #dce5f2;
        --accent: #1267e8;
        --accent-hover: #0b57cb;
        --accent-soft: #e8f2ff;
        --table-head: #dceafe;
        --table-band: #f7faff;
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
        font-size: 1.45rem;
        line-height: 1.25;
        font-weight: 700;
        color: var(--text);
        padding: 0.15rem 0 0.75rem;
        border-bottom: 1px solid var(--border-soft);
        margin-bottom: 1rem;
    }

    .card {
        background: var(--surface);
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: none;
        border: 1px solid var(--border-soft);
    }

    .home-filter-card {
        background: #ffffff;
        border: 1px solid #d8e3f2;
        border-radius: 8px;
        padding: 0.7rem 0.78rem 0.58rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }

    [class*="_filter_card"][data-testid="stVerticalBlockBorderWrapper"],
    [class*="_filter_card"] [data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff;
        border: 1px solid var(--border-soft);
        border-radius: 8px;
        padding: 0.95rem 1rem 0.85rem;
        margin-bottom: 0.85rem;
        box-shadow: none;
    }

    [class*="_filter_card"][data-testid="stVerticalBlock"],
    [class*="_filter_card"] [data-testid="stVerticalBlock"] {
        gap: 0.5rem;
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
        font-size: 0.86rem;
        color: #17345f;
        font-weight: 800;
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
        color: #42526a;
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
        margin-left: -3.1rem !important;
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
        border: 1px solid var(--border-soft) !important;
        background: #f8fafc !important;
        color: #334155 !important;
        min-height: 2rem !important;
        padding: 0.1rem 0.72rem !important;
    }

    [class*="_filter_year_pills"] [kind="pillsActive"],
    [class*="_filter_month_pills"] [kind="pillsActive"],
    [class*="_filter_group_pills"] [kind="pillsActive"] {
        background: rgba(0, 113, 227, 0.14) !important;
        border-color: rgba(0, 113, 227, 0.35) !important;
        color: #0f4f9d !important;
    }

    [class*="_filter_group_pills"] div[role="radiogroup"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 0.45rem !important;
        padding-bottom: 0.1rem;
        scrollbar-width: thin;
    }

    [class*="_filter_group_pills"] [data-testid^="stBaseButton"] {
        flex: 0 0 auto !important;
    }

    [class*="_summary_mode_pills"] [data-testid^="stBaseButton"] {
        border-radius: 8px !important;
        border: 1px solid rgba(37, 99, 235, 0.28) !important;
        background: rgba(37, 99, 235, 0.08) !important;
        color: #0f4f9d !important;
        min-height: 2.22rem !important;
        padding: 0.12rem 0.75rem !important;
    }

    [class*="_summary_mode_pills"] [kind="pillsActive"] {
        background: rgba(37, 99, 235, 0.12) !important;
        border-color: rgba(37, 99, 235, 0.35) !important;
        color: #0f4f9d !important;
    }

    [class*="_summary_mode_pills"] [data-testid^="stBaseButton"] p {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }

    [class*="_filter_apply"] button,
    [class*="_filter_reset"] button,
    [class*="_filter_toggle"] button {
        min-height: 2.02rem !important;
        border-radius: 7px !important;
        font-weight: 650 !important;
        padding: 0.1rem 0.5rem !important;
        font-size: 0.76rem !important;
        margin-top: 1.8rem !important;
    }

    [class*="_filter_apply"] button {
        background: #0b74de !important;
        border-color: #0b74de !important;
    }

    [class*="_company_units"] [data-baseweb="select"] {
        min-height: 2.02rem !important;
    }

    [class*="_company_units"] [data-baseweb="tag"] {
        max-width: 12rem !important;
    }

    .metric-card {
        background: var(--surface);
        border-radius: 8px;
        padding: 1.15rem;
        text-align: left;
        border: 1px solid var(--border-soft);
        box-shadow: none;
    }

    .metric-card .icon {
        font-size: 1.35rem;
        margin-bottom: 0.45rem;
    }

    .metric-card .value {
        font-size: 1.7rem;
        line-height: 1.15;
        font-weight: 700;
        color: var(--text);
    }

    .metric-card .label {
        font-size: 0.82rem;
        color: var(--muted);
        font-weight: 500;
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
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.78rem;
        padding: 0.2rem 0.52rem;
        min-height: 1.9rem;
        border: 1px solid var(--border);
        transition: none !important;
        box-shadow: none;
    }

    div.stButton > button [class*="material-symbols"] {
        font-size: 0.9rem !important;
        line-height: 1 !important;
        margin-right: 0.2rem !important;
        opacity: 0.9;
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
    }

    div.stButton > button[kind="primary"]:hover {
        background: var(--accent-hover);
        border-color: var(--accent-hover);
        color: #ffffff;
    }

    div[data-testid="stDataFrame"],
    div[data-testid="stDataEditor"] {
        border-radius: 6px;
        overflow: hidden;
        border: 1px solid #d5e1f0;
        box-shadow: none;
        background: #ffffff;
    }

    div[data-testid="stDataFrame"] {
        min-height: 15rem;
    }

    div[data-testid="stDataFrame"] thead tr th {
        background: var(--table-head);
        color: #10233f;
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.55rem 0.75rem;
        border-bottom: 1px solid #bcd2ee;
    }

    div[data-testid="stDataFrame"] tbody tr:nth-child(even) {
        background: var(--table-band);
    }

    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="columnheader"] {
        background: var(--table-head) !important;
        color: #10233f !important;
        font-weight: 700 !important;
        font-size: 0.78rem !important;
    }

    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataEditor"] [role="gridcell"] {
        font-size: 0.78rem !important;
        color: #122033 !important;
    }

    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stMultiSelect"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stFileUploader"] label,
    div[data-testid="stRadio"] label {
        color: #4b5f78 !important;
        font-size: 0.76rem !important;
        font-weight: 650 !important;
        margin-bottom: 0.12rem !important;
    }

    div[data-baseweb="select"] > div,
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {
        min-height: 2.2rem !important;
        border-radius: 6px !important;
        border-color: #d5e1f0 !important;
        background: #ffffff !important;
        font-size: 0.82rem !important;
        color: #122033 !important;
    }

    div[data-baseweb="select"] span,
    div[data-testid="stTextInput"] input::placeholder {
        font-size: 0.82rem !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.95rem;
        border-bottom: 1px solid #d5e1f0;
    }

    .stTabs [data-baseweb="tab"] {
        height: 2.35rem;
        padding: 0 0.25rem;
        color: #42526a;
        font-size: 0.84rem;
        font-weight: 650;
    }

    .stTabs [aria-selected="true"] {
        color: var(--accent) !important;
        border-bottom: 2px solid var(--accent) !important;
    }

    div[data-testid="stFileUploader"] {
        border-radius: 8px;
        border: 1px dashed #b9b9c0;
        background: #fbfbfd;
        padding: 1rem;
    }

    div[data-testid="stFileUploader"]:hover {
        border-color: var(--accent);
        background: #f7fbff;
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
        border-bottom: 1px dashed #cad5df;
        transition: color .15s ease, border-color .15s ease;
    }

    .bi-kpi-value-link:hover {
        color: var(--accent);
        border-bottom-color: var(--accent);
    }

    .bi-kpi-delta {
        color: #52606d;
        font-size: 0.76rem;
        margin-top: 0.32rem;
        width: 100%;
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
        font-size: 0.74rem !important;
        font-weight: 650 !important;
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
        font-size: 1.02rem !important;
        font-weight: 760 !important;
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
        font-size: 0.86rem !important;
        font-weight: 520 !important;
        border-radius: 9px !important;
    }

    [class*="st-key-nav_"]:not([class*="st-key-nav_module_toggle_"]) button[kind="primary"] {
        background: rgba(59,130,246,0.18) !important;
        border-color: transparent !important;
        color: #bfdbfe !important;
        font-weight: 650 !important;
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

    .bi-section-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.8rem 0;
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


def _render_bi_kpi_grid(kpis: list[dict], drill_label_map: dict[str, str] | None = None) -> None:
    drill_label_map = drill_label_map or {}
    cards = []
    for kpi in kpis:
        label = str(kpi.get("label", ""))
        delta = _fmt_kpi_delta(kpi)
        delta_html = f'<div class="bi-kpi-delta">{_html(delta)}</div>' if delta else ""
        value_text = _fmt_kpi_value(kpi)
        drill_key = drill_label_map.get(label)
        if drill_key:
            value_markup = (
                f'<a class="bi-kpi-value-link" href="?drill_metric={_html(drill_key)}" '
                f'title="点击下钻">{_html(value_text)}</a>'
            )
        else:
            value_markup = _html(value_text)
        cards.append(
            f"""
            <div class="bi-kpi-card {_kpi_card_class(kpi)}">
                <div class="bi-kpi-label">{_html(label)}</div>
                <div class="bi-kpi-value">{value_markup}</div>
                {delta_html}
            </div>
            """
        )
    _render_html(f'<div class="bi-kpi-grid">{"".join(cards)}</div>')


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
        "经营看板": ["首页", "利润表总览驾驶舱", "利润表明细（原表）", "费用科目分析", "多维图片简报", "多期对比"],
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
        "组织与系统": ["公司层级", "系统管理"],
    },
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
    "合并报表": "合并报表",
    "多期对比": "多期对比",
    "盈亏平衡测算": "盈亏平衡测算",
    "基础设置": "基础设置",
    "公司层级": "公司层级",
    "系统管理": "系统管理",
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
    page = str(current or "首页")
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


def render_sidebar():
    with st.sidebar:
        st.markdown(
            """<div class="sidebar-brand"><div class="app-title">财务数据仓库</div><div class="app-subtitle">Finance Workspace</div></div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        module_sections = NAV_MODULE_SECTIONS
        labels = NAV_LABELS
        current = _normalize_sidebar_page(st.session_state.get("nav_choice", "首页"))
        if st.session_state.get("nav_choice") != current:
            st.session_state.nav_choice = current
        page_module = _sidebar_page_module_map(module_sections)
        active_module = page_module.get(current, next(iter(module_sections)))
        open_key = "nav_open_modules"
        if open_key not in st.session_state:
            st.session_state[open_key] = [active_module]
        open_modules = [
            module for module in st.session_state.get(open_key, [])
            if module in module_sections
        ]
        st.session_state[open_key] = open_modules
        st.session_state.nav_module = active_module

        for module_name, sections in module_sections.items():
            is_active_module = module_name == active_module
            is_expanded = module_name in st.session_state[open_key]
            arrow = "▾" if is_expanded else "▸"
            module_icons = {"经营中心": "📊", "数据中心": "🗂", "财务中心": "💰", "基础设置": "⚙"}
            button_type = "primary" if (is_active_module or is_expanded) else "secondary"
            if st.button(
                f"{module_icons.get(module_name, '▪')}  {module_name}  {arrow}",
                key=f"nav_module_toggle_{module_name}",
                type=button_type,
                use_container_width=True,
            ):
                open_set = set(st.session_state[open_key])
                if module_name in open_set:
                    open_set.remove(module_name)
                else:
                    open_set.add(module_name)
                st.session_state[open_key] = [item for item in module_sections if item in open_set]
                st.rerun()

            if module_name not in st.session_state[open_key]:
                continue

            for section, items in sections.items():
                st.markdown(f'<div class="nav-section-title">{section}</div>', unsafe_allow_html=True)
                for item in items:
                    item_type = "primary" if current == item else "secondary"
                    if st.button(labels[item], key=f"nav_{item}", type=item_type, use_container_width=True):
                        st.session_state.nav_choice = item
                        st.session_state.nav_module = page_module.get(item, module_name)
                        st.rerun()

        st.markdown('<div class="sidebar-note">本地数据仓库 · SQLite</div>', unsafe_allow_html=True)
    return current

# ============================================================================
# 页面模块
# ============================================================================

HOME_DRILL_CONFIG: dict[str, dict[str, str]] = {
    "revenue": {
        "label": "本月收入",
        "title": "收入构成明细 (第二级)",
        "source": "income",
        "item_name": INCOME_ITEM,
        "current_col": "本月收入",
        "previous_col": "上月收入",
        "root": "集团总收入",
    },
    "net_profit": {
        "label": "本月净利润",
        "title": "净利润构成明细 (第二级)",
        "source": "income",
        "item_name": NET_PROFIT_ITEM,
        "current_col": "本月净利润",
        "previous_col": "上月净利润",
        "root": "集团总利润",
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


def _resolve_scope_company_codes(scope_code: str | None, business_group: str | None = None) -> list[str]:
    business_group_value = str(business_group).strip() if business_group is not None else None
    if scope_code:
        codes = [str(code) for code in get_company_list_for_summary(scope_code) if str(code)]
        if not codes:
            base_codes = [scope_code]
        else:
            placeholders = ", ".join(f":code_{idx}" for idx, _ in enumerate(codes))
            params = {f"code_{idx}": code for idx, code in enumerate(codes)}
            df = execute_sql(
                f"""
                SELECT code
                FROM companies
                WHERE status = 1
                  AND is_consolidated = 1
                  AND code IN ({placeholders})
                """,
                params,
            )
            base_codes = df["code"].astype(str).tolist() if len(df) else [scope_code]
    else:
        df = execute_sql(
            """
            SELECT code
            FROM companies
            WHERE status = 1 AND is_consolidated = 1
            ORDER BY tree_path, code
            """
        )
        base_codes = df["code"].astype(str).tolist() if len(df) else []

    if (
        not business_group_value
        or business_group_value in {"不限", "全部", "*", "??"}
        or business_group_value.replace("?", "") == ""
    ):
        return base_codes

    if not base_codes:
        return base_codes

    params = {"business_group": business_group_value}
    holders = []
    for idx, code in enumerate(base_codes):
        key = f"base_code_{idx}"
        params[key] = code
        holders.append(f":{key}")

    group_df = execute_sql(
        f"""
        SELECT code
        FROM companies
        WHERE code IN ({', '.join(holders)})
          AND code IN (
              SELECT CAST(company_id AS TEXT)
              FROM dim_company
              WHERE COALESCE(NULLIF(TRIM(business_group), ''), '未分组') = :business_group
          )
        ORDER BY tree_path, code
        """,
        params,
    )
    return group_df["code"].astype(str).tolist() if len(group_df) else []


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
def _get_workspace_company_options(business_group: str | None = None) -> pd.DataFrame:
    business_group_value = str(business_group or "").strip()
    group_filter = ""
    params: dict[str, str] = {}
    if business_group_value and business_group_value not in {"不限", "全部", "*"}:
        group_filter = """
          AND COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') = :business_group
        """
        params["business_group"] = business_group_value

    return execute_sql(
        f"""
        SELECT
            CAST(c.code AS TEXT) AS code,
            COALESCE(NULLIF(TRIM(c.name), ''), CAST(c.code AS TEXT)) AS name,
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS business_group
        FROM companies c
        LEFT JOIN dim_company d
          ON CAST(d.company_id AS TEXT) = CAST(c.code AS TEXT)
        WHERE c.status = 1
          AND c.is_consolidated = 1
          {group_filter}
        ORDER BY c.tree_path, c.code
        """,
        params,
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
    base_codes = _resolve_scope_company_codes(scope_code, business_group=filters.get("business_group"))
    selected_codes = [str(code) for code in filters.get("selected_company_codes", []) if str(code)]
    if not selected_codes:
        return base_codes
    selected_set: set[str] = set()
    for code in selected_codes:
        try:
            selected_set.update(str(item) for item in get_company_list_for_summary(code) if str(item))
        except Exception:
            selected_set.add(code)
    if not selected_set:
        selected_set = set(selected_codes)
    return [code for code in base_codes if code in selected_set]


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
        st.selectbox("业态", ["不限"] + BUSINESS_TYPE_OPTIONS, key=f"{key_prefix}_business_type")
    with region_col:
        st.selectbox("区域", ["不限"] + REGION_OPTIONS, key=f"{key_prefix}_region")
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

    if st.session_state.get(f"{key_prefix}_filter_year_pills") in year_options:
        st.session_state[year_key] = st.session_state[f"{key_prefix}_filter_year_pills"]
    if st.session_state.get(f"{key_prefix}_filter_month_pills") in month_options:
        st.session_state[month_key] = st.session_state[f"{key_prefix}_filter_month_pills"]
    if st.session_state.get(f"{key_prefix}_filter_group_pills") in group_options:
        st.session_state[group_key] = st.session_state[f"{key_prefix}_filter_group_pills"]

    selected_year = st.session_state[year_key]
    selected_month = st.session_state[month_key]
    company_options_df = _get_workspace_company_options(st.session_state[group_key])
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
                note,
            )
    result = {
        "summary_mode": st.session_state[summary_key],
        "business_group": st.session_state[group_key],
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
) -> None:
    if not options:
        return

    current_value = selected if selected in options else options[0]
    widget_key = f"{row_key}_pills"

    if widget_key in st.session_state and st.session_state[widget_key] not in options:
        st.session_state[widget_key] = current_value
    if widget_key not in st.session_state:
        st.session_state[widget_key] = current_value

    label_col, pills_col = st.columns([1.05, 16.65], gap="small")
    with label_col:
        st.markdown(f'<div class="quick-filter-label">{_html(label)}：</div>', unsafe_allow_html=True)
    with pills_col:
        picked = st.pills(
            label,
            options,
            selection_mode="single",
            default=current_value,
            key=widget_key,
            label_visibility="collapsed",
            width="content",
        )
        st.session_state[session_key] = picked if picked in options else current_value


def _query_metric_by_group(
    period: str,
    company_codes: list[str],
    source: str,
    item_name: str,
) -> pd.DataFrame:
    if source == "income":
        table = "income_statement"
        alias = "f"
        value_col = "period1_value"
    elif source == "balance":
        table = "balance_sheet"
        alias = "f"
        value_col = "ending_balance"
    else:
        return pd.DataFrame(columns=["业务板块", "数值"])

    params = {"period": period, "item_name": item_name}
    company_sql = _company_filter_clause(alias, company_codes, params, f"drill_{source}")
    return execute_sql(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组') AS 业务板块,
            SUM({alias}.{value_col}) AS 数值
        FROM {table} {alias}
        LEFT JOIN dim_company d
          ON CAST(d.company_id AS TEXT) = CAST({alias}.company_code AS TEXT)
        WHERE {alias}.period = :period
          AND {alias}.item_name = :item_name
          {company_sql}
        GROUP BY COALESCE(NULLIF(TRIM(d.business_group), ''), '未分组')
        """,
        params,
    )


def _load_metric_drilldown(
    metric_key: str,
    period: str,
    prev_period: str | None,
    company_codes: list[str],
) -> pd.DataFrame:
    cfg = HOME_DRILL_CONFIG.get(metric_key)
    if not cfg:
        return pd.DataFrame()

    current_df = _query_metric_by_group(
        period,
        company_codes,
        cfg["source"],
        cfg["item_name"],
    ).rename(columns={"数值": "本期值"})
    if len(current_df) == 0:
        return current_df

    if prev_period:
        prev_df = _query_metric_by_group(
            prev_period,
            company_codes,
            cfg["source"],
            cfg["item_name"],
        ).rename(columns={"数值": "上期值"})
    else:
        prev_df = pd.DataFrame(columns=["业务板块", "上期值"])

    merged = current_df.merge(prev_df, on="业务板块", how="left")
    merged["本期值"] = pd.to_numeric(merged["本期值"], errors="coerce").fillna(0.0)
    merged["上期值"] = pd.to_numeric(merged["上期值"], errors="coerce").fillna(0.0)
    merged["绝对值"] = merged["本期值"].abs()
    total_abs = _safe_float(merged["绝对值"].sum())
    merged["占比(%)"] = 0.0
    if total_abs > 0:
        merged["占比(%)"] = (merged["绝对值"] / total_abs * 100).round(2)
    merged = merged.sort_values(by="占比(%)", ascending=False).reset_index(drop=True)

    return merged.rename(
        columns={
            "本期值": cfg["current_col"],
            "上期值": cfg["previous_col"],
        }
    )


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
    except Exception as exc:
        st.error(f"首页指标计算失败: {exc}")
        return

    income = dashboard.get("income", {})
    balance = dashboard.get("balance", {})
    budget = dashboard.get("budget", {})
    funds = dashboard.get("funds", pd.DataFrame())
    ranking = dashboard.get("ranking", pd.DataFrame())
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
    _render_bi_kpi_grid(kpis, drill_label_map=drill_label_map)
    st.caption("提示：点击 KPI 数值可下钻到下一层级，查看构成占比与树状图。")

    drill_metric = _get_query_param("drill_metric")
    if drill_metric in HOME_DRILL_CONFIG:
        _clear_query_param("drill_metric")
        show_metric_drilldown_dialog(
            drill_metric,
            period,
            prev_period,
            scope_code,
            scope_label,
            business_group=selected_group,
            company_codes=filtered_company_codes,
        )

    _render_html(
        f"""
        <div class="bi-section-grid">
            {_render_budget_panel(budget)}
            {_render_funds_panel(balance, income)}
            {_render_health_panel(completeness, anomalies, balance)}
        </div>
        """
    )

    rank_body = _bar_rows_html(
        ranking,
        "公司",
        "收入",
        8,
        _fmt_money_compact,
        positive_good=True,
    )
    funds_body = _bar_rows_html(
        funds,
        "公司",
        "可使用周转金",
        8,
        _fmt_money_compact,
        positive_good=True,
    )
    alerts_body = _alerts_html(anomalies)
    summary_body = f"""
        <div class="bi-micro">
            <div class="bi-micro-row"><div class="label">本月收入</div><div class="value">{_html(_fmt_money_compact(income.get("revenue")))}</div></div>
            <div class="bi-micro-row"><div class="label">本月净利润</div><div class="value">{_html(_fmt_money_compact(income.get("net_profit")))}</div></div>
            <div class="bi-micro-row"><div class="label">净利率</div><div class="value">{_html(_fmt_percent(income.get("net_margin")))}</div></div>
            <div class="bi-micro-row"><div class="label">资产负债平衡差</div><div class="value">{_html(_fmt_money_compact(balance.get("balance_gap")))}</div></div>
        </div>
    """
    rank_panel = _panel_html("校区收入排行", "先看规模，再看利润和净利率下钻", rank_body)
    funds_panel = _panel_html("资金周转风险", "按可使用周转金从低到高排序", funds_body)
    alerts_panel = _panel_html("异常事项", "负周转、亏损和资产负债不平会优先显示", alerts_body)
    summary_panel = _panel_html("经营摘要", "给经营分析会的第一屏结论", summary_body)
    _render_html(
        f"""
        <div class="bi-two-col">
            {rank_panel}
            {funds_panel}
        </div>
        <div class="bi-two-col">
            {alerts_panel}
            {summary_panel}
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
    st.markdown(sheet.html, unsafe_allow_html=True)


def render_multi_picture_brief():
    st.markdown('<div class="page-header">图片简报</div>', unsafe_allow_html=True)
    brief_type = st.radio(
        "简报类型",
        ["月报", "本年累计"],
        horizontal=True,
        label_visibility="collapsed",
        key="multi_picture_brief_type",
    )
    if brief_type == "月报":
        _render_fixed_template_sheet("图片简报", "multi_picture_template_month", min_col=2, max_col=9)
    else:
        _render_fixed_template_sheet("图片简报", "multi_picture_template_ytd", min_col=13, max_col=20)


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
                "2026合计": amount,
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
                "2026合计": amount,
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
        --page-bg:#f5f7fb;--card-bg:#ffffff;--table-header-bg:#eaf2ff;
        --summary-row-bg:#eef5ff;--profit-row-bg:#fff0f0;--danger:#f5222d;
        --success:#16a34a;--warning:#faad14;--border:#d9e2ef;
        --text-main:#10233f;--text-secondary:#5b6b82;
      }
      .profit-original-shell{margin-top:12px;color:var(--text-main);}
      .profit-original-action{
        display:grid;grid-template-columns:minmax(320px,1fr) auto;gap:12px;align-items:center;
        background:var(--card-bg);border:1px solid var(--border);border-radius:8px;
        padding:14px 16px;margin-bottom:12px;box-shadow:0 8px 22px rgba(16,35,63,.04);
      }
      .profit-original-meta-title{font-size:17px;font-weight:800;color:var(--text-main);line-height:1.3;}
      .profit-original-meta-sub{margin-top:6px;color:var(--text-secondary);font-size:12.5px;line-height:1.6;}
      .profit-original-meta-sub span{display:inline-flex;align-items:center;margin-right:14px;white-space:nowrap;}
      .profit-original-card{
        background:var(--card-bg);border:1px solid var(--border);border-radius:8px;
        overflow:visible;box-shadow:0 10px 24px rgba(16,35,63,.045);
      }
      .profit-original-card-head{
        display:flex;align-items:center;justify-content:space-between;gap:12px;
        padding:12px 14px;border-bottom:1px solid var(--border);background:#fbfdff;
      }
      .profit-original-card-title{font-size:15px;font-weight:800;color:var(--text-main);}
      .profit-original-card-tip{font-size:12px;color:var(--text-secondary);}
      .profit-original-table-scroll{max-height:none;overflow:visible;background:#fff;}
      .profit-original-table{width:100%;min-width:0;border-collapse:separate;border-spacing:0;font-size:13px;table-layout:fixed;}
      .profit-original-table th{
        height:44px;background:var(--table-header-bg);
        color:var(--text-main);font-size:13px;font-weight:700;text-align:center;
        border-right:1px solid var(--border);border-bottom:1px solid var(--border);
        padding:0 10px;white-space:nowrap;
      }
      .profit-original-table td{
        height:42px;border-right:1px solid var(--border);border-bottom:1px solid var(--border);
        padding:8px 10px;background:#fff;text-align:right;white-space:nowrap;
        color:var(--text-main);font-variant-numeric:tabular-nums;
      }
      .profit-original-table th:first-child,.profit-original-table td:first-child{
        text-align:center;border-left:1px solid var(--border);
      }
      .profit-original-table td:first-child{background:#fff;font-weight:700;}
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


def _profit_original_display_rows(rows: list[dict], mode: str) -> list[dict]:
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
                "费用科目": row["费用科目"],
                "合计": _safe_float(row.get("合计")),
                "占费用比": _safe_float(row.get("占费用比")) * 100 if row.get("占费用比") is not None else None,
                "占收入比": _safe_float(row.get("占收入比")) * 100 if row.get("占收入比") is not None else None,
                "上月": row.get("上月"),
                "环比": _safe_float(row.get("环比")) * 100 if row.get("环比") is not None else None,
                "备注": row.get("备注", ""),
            }
            for row in rows
        ]
    )


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
    rows = operating_rows if operating_rows is not None else _profit_original_table_rows(detail_df, previous_detail_df)
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
    body_rows = []
    for row in visible_rows:
        cells = [
            f'<td>{_html(row["费用科目"])}</td>',
            f'<td>{_profit_original_amount_link(row["row_idx"], "total", row["合计"])}</td>',
            f'<td>{_html(_operating_pct_cell(row["占费用比"]))}</td>',
            f'<td>{_html(_operating_pct_cell(row["占收入比"]))}</td>',
            f'<td>{_profit_original_amount_link(row["row_idx"], "previous", row["上月"])}</td>',
            f'<td>{_profit_original_mom_cell(row["环比"])}</td>',
            f'<td class="remark-cell">{_html(_profit_original_remark(row, company_codes))}</td>',
        ]
        body_rows.append(f'<tr class="{_profit_original_row_class(row)}">{"".join(cells)}</tr>')
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
<colgroup>
<col style="width:18%"><col style="width:13%"><col style="width:10%">
<col style="width:10%"><col style="width:14%"><col style="width:10%">
<col style="width:25%">
</colgroup>
<thead>
<tr>
<th>费用科目</th><th>合计</th><th>占费用比</th><th>占收入比</th><th>上月</th><th>环比</th><th>备注</th>
</tr>
</thead>
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
    previous_source_df = (
        get_operating_summary_source_detail(previous_period, company_codes)
        if previous_period
        else pd.DataFrame()
    )
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


def render_expense_subject_analysis():
    ctx = _profit_page_context(
        "expense_subject",
        "费用科目分析",
        "财务主管按费用科目定位异常、备注、数据来源和近 6 个月趋势。",
    )
    if not ctx:
        return
    rows = _operating_table_rows(ctx["detail_df"], ctx["previous_detail_df"])
    subjects = [row["费用科目"] for row in rows] or ["暂无科目"]
    left, middle, right = st.columns([0.82, 1.75, 1.18], gap="large")
    with left:
        st.markdown('<div class="home-filter-title">费用科目树</div>', unsafe_allow_html=True)
        selected_subject = st.radio(
            "费用科目树",
            subjects,
            label_visibility="collapsed",
            key="expense_subject_tree",
        )
    selected_row = next((row for row in rows if row["费用科目"] == selected_subject), rows[0] if rows else None)
    with middle:
        st.markdown('<div class="home-filter-title">科目明细表</div>', unsafe_allow_html=True)
        if not rows:
            st.info("暂无费用科目数据。")
        else:
            detail_rows = []
            for row in rows:
                detail_rows.append(
                    {
                        "费用科目": row["费用科目"],
                        "本月": row["2026合计"],
                        "占费用比": _safe_float(row["占费用比"]) * 100,
                        "占收入比": _safe_float(row["占收入比"]) * 100,
                        "环比": _safe_float(row["环比"]) * 100 if row["环比"] is not None else None,
                        "异常说明": row["备注"],
                    }
                )
            st.dataframe(
                pd.DataFrame(detail_rows),
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={
                    "本月": st.column_config.NumberColumn("本月", format="%,.2f"),
                    "占费用比": st.column_config.NumberColumn("占费用比", format="%.1f%%"),
                    "占收入比": st.column_config.NumberColumn("占收入比", format="%.1f%%"),
                    "环比": st.column_config.NumberColumn("环比", format="%.1f%%"),
                },
            )
            drill_col, source_col = st.columns(2)
            with drill_col:
                if st.button("查看金额明细", type="primary", use_container_width=True):
                    st.session_state["expense_show_detail"] = True
            with source_col:
                if st.button("查看来源", use_container_width=True):
                    st.session_state["expense_show_sources"] = True
            if st.session_state.get("expense_show_detail") and selected_row:
                with st.expander("金额明细", expanded=True):
                    amount_detail = pd.DataFrame(
                        [
                            ["统计期间", ctx["period"]],
                            ["组织主体", ctx["scope_label"]],
                            ["费用科目", selected_row["费用科目"]],
                            ["当前金额", f"{_safe_float(selected_row['2026合计']):,.2f}"],
                            ["数据来源", "Excel导入 / 系统计算"],
                            ["导入批次号", "IMP-202603-001"],
                            ["原始文件名", "2026年损益表.xlsx"],
                            ["原始 Sheet 名", "损益表"],
                            ["原始行号", "12"],
                            ["原始列名", "2026合计"],
                            ["原始单元格位置", "H12"],
                            ["原始金额", f"{_safe_float(selected_row['2026合计']):,.2f}"],
                            ["调整金额", "0.00"],
                            ["最终金额", f"{_safe_float(selected_row['2026合计']):,.2f}"],
                            ["备注", selected_row["备注"] or "Excel导入"],
                            ["操作人", "系统导入"],
                            ["更新时间", "2026-03-31 23:59:59"],
                        ],
                        columns=["字段", "内容"],
                    )
                    st.table(amount_detail)
    with right:
        st.markdown('<div class="home-filter-title">分析辅助区</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**异常提醒**")
            if ctx["alerts"]:
                for item in ctx["alerts"]:
                    st.warning(item.get("text", ""))
            else:
                st.success("当前范围未发现明显异常。")
        with st.container(border=True):
            st.markdown("**备注模板**")
            st.button("需要追溯导入来源/项目明细", use_container_width=True)
            st.button("水电费可单独标注异常", use_container_width=True)
            st.button("建议拆工资/社保/绩效", use_container_width=True)
        with st.container(border=True):
            st.markdown("**数据来源**")
            source_rows = pd.DataFrame(
                [
                    ["Excel导入", "IMP-202603-001", "2026年损益表.xlsx", "损益表!H12", 1231653.00, "查看来源"],
                    ["手工调整", "ADJ-202603-002", "-", "人工录入", -20000.00, "查看来源"],
                    ["系统计算", "CALC-202603-001", "-", "成本费用合计公式", 24888280.24, "查看来源"],
                ],
                columns=["来源类型", "导入批次", "原始文件", "原表位置", "金额", "操作"],
            )
            st.table(source_rows)
        with st.container(border=True):
            st.markdown("**近 6 个月趋势**")
            if len(ctx["trend_df"]):
                st.line_chart(ctx["trend_df"].set_index("期间")[["收入合计", "成本费用合计", "净利润"]])
            else:
                st.info("暂无趋势数据。")


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
        _render_operating_original_design(period, scope_label, company_codes, detail_df, previous_detail_df)
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
            key="import_wizard_files",
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

            st.markdown("##### 入库报告")
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
            st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)
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
    # 全选时覆盖月份
    if all_months:
        sel_months = months

    if st.button("查询报表", type="primary", icon=":material/monitoring:", use_container_width=True):
        if not sel_year or not sel_months:
            st.toast("请选择年份和月份", icon="⚠️"); return
        sel_periods = [f"{sel_year}{m}" for m in sel_months]

        with st.spinner("⏳ 查询中..."):
            period_ph = ",".join([f"'{p}'" for p in sel_periods])
            df = execute_sql(f"""
                SELECT COALESCE(ab.original_name, c.name, ab.company_code) AS original_name,
                       ab.item_name,
                       CASE WHEN :is_all = 1 THEN ab.cumulative_value ELSE ab.period1_value END AS period1_value,
                       ab.sort_order
                FROM income_statement ab
                LEFT JOIN companies c ON ab.company_code = c.code
                WHERE ab.period IN ({period_ph})
                ORDER BY ab.sort_order
            """, {"is_all": 1 if all_months else 0})
        if len(df) > 0:
            st.toast(f"已找到损益表数据", icon="✅")
            df["row_idx"] = df["sort_order"] // 1000
            # 透视：行=科目名，列=原始公司名
            pivot = df.pivot_table(
                index=["item_name", "row_idx"],
                columns="original_name",
                values="period1_value",
                aggfunc="sum"
            ).fillna(0).reset_index()
            pivot = pivot.sort_values("row_idx").drop(columns="row_idx")
            pivot = pivot.rename(columns={"item_name": "项目"})

            # 固定模板列顺序
            col_order = ["项目"]
            for c in df.sort_values("sort_order")["original_name"].unique():
                if c in pivot.columns:
                    col_order.append(c)
            pivot = pivot[[c for c in col_order if c in pivot.columns]]

            # 毛利/净利率行数值 ×100 并转为百分比字符串
            pct_items = pivot["项目"].str.contains("毛利|净利率", na=False)
            for col in pivot.columns:
                if col != "项目":
                    pivot[col] = pd.to_numeric(pivot[col], errors="coerce").fillna(0).astype(object)
                    for idx in pivot.index:
                        val = pivot.at[idx, col]
                        if pct_items[idx]:
                            v = float(val) * 100
                            pivot.at[idx, col] = f"{v:.0f}%" if abs(v - round(v)) < 0.001 else f"{v:.1f}%"
                        else:
                            pivot.at[idx, col] = f"{float(val):,.2f}"

            # 配置列格式（全部用TextColumn）
            col_config = {"项目": st.column_config.TextColumn("项目", width="medium")}
            for c in pivot.columns:
                if c != "项目":
                    col_config[c] = st.column_config.TextColumn(c, width="small")

            # 配置列格式
            col_config = {"项目": st.column_config.TextColumn("项目", width="medium")}
            for c in pivot.columns:
                if c != "项目":
                    col_config[c] = st.column_config.NumberColumn(c, format="%,.2f")

            st.dataframe(pivot, use_container_width=True, hide_index=True, height=600,
                         column_config=col_config)

            # 导出 Excel（按模板格式）
            with st.spinner("⏳ 生成导出文件..."):
                fpath = export_income_statement_pivot(pivot, sel_year)
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
                st.dataframe(df, use_container_width=True, hide_index=True, height=500, column_config=config)
            else:
                st.toast("未查询到数据", icon="⚠️")

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


def _render_base_settings_org():
    st.info("组织架构用于维护公司上下级、组织树和合并范围；不要用它调整经营分析业务模块。")
    render_company_hierarchy()


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
    tabs = st.tabs(["首页", "组织架构", "公司档案", "名称口径", "归集规则", "导入问题池", "变更记录"])
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
        "盈亏平衡测算": render_break_even_calculator,
        "合并报表": render_consolidated,
        "多期对比": render_multi_period,
        "基础设置": render_base_settings,
        "公司层级": render_company_hierarchy,
        "系统管理": render_admin,
    }
    page_map.get(choice, render_home)()
    render_footer()

if __name__ == "__main__":
    main()
