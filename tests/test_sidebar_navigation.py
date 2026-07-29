import inspect
from pathlib import Path

import app


BASE_SETTINGS_KEYS = [
    "base_settings.overview",
    "base_settings.organization",
    "base_settings.company_profile",
    "base_settings.name_standard",
    "base_settings.collection_rules",
    "base_settings.import_issues",
    "base_settings.change_log",
]


def test_sidebar_has_four_top_level_modules_and_base_settings_entries():
    assert list(app.NAV_MODULE_SECTIONS) == ["经营中心", "数据中心", "财务中心", "基础设置"]
    assert "基础设置" in app.NAV_MODULE_SECTIONS
    assert app.NAV_MODULE_SECTIONS["基础设置"] == {"基础设置": BASE_SETTINGS_KEYS}
    assert [app.NAV_LABELS[key] for key in BASE_SETTINGS_KEYS] == [
        "首页",
        "组织架构",
        "公司档案",
        "名称口径",
        "归集规则",
        "导入问题池",
        "变更记录",
    ]
    assert app._sidebar_page_module_map()["base_settings.company_profile"] == "基础设置"


def test_business_center_uses_budget_entry_in_profit_dashboard_slot():
    business_entries = app.NAV_MODULE_SECTIONS["经营中心"]["经营看板"]

    assert business_entries[1] == "全面预算"
    assert "资金预警" in business_entries
    assert "利润表总览驾驶舱" not in business_entries
    assert business_entries.count("全面预算") == 1
    assert business_entries.count("资金预警") == 1


def test_sidebar_expanded_state_keeps_multiple_modules_open():
    expanded = app._sidebar_expanded_state(
        "base_settings.company_profile",
        {"经营中心": True, "数据中心": False, "财务中心": True, "基础设置": True},
    )

    assert expanded["经营中心"] is True
    assert expanded["财务中心"] is True
    assert expanded["基础设置"] is True
    assert expanded["数据中心"] is False


def test_sidebar_toggle_only_changes_one_module():
    expanded = {"经营中心": True, "数据中心": True, "财务中心": False, "基础设置": True}

    updated = app._toggle_sidebar_module(expanded, "基础设置")

    assert updated["基础设置"] is False
    assert updated["经营中心"] is True
    assert updated["数据中心"] is True
    assert updated["财务中心"] is False


def test_sidebar_current_page_defaults_its_module_open():
    expanded = app._sidebar_expanded_state("base_settings.organization", {})

    assert expanded["基础设置"] is True
    assert expanded["经营中心"] is False


def test_sidebar_preserves_manual_collapse_of_current_module():
    expanded = app._sidebar_expanded_state(
        "base_settings.organization",
        {"经营中心": True, "数据中心": False, "财务中心": False, "基础设置": False},
    )

    assert expanded["基础设置"] is False
    assert expanded["经营中心"] is True


def test_sidebar_legacy_pages_redirect_to_base_settings_keys():
    assert app._normalize_sidebar_page("基础设置") == "base_settings.overview"
    assert app._normalize_sidebar_page("公司层级") == "base_settings.organization"
    assert app._normalize_sidebar_page("系统管理") == "base_settings.overview"


def test_sidebar_render_uses_buttons_not_single_select_pills():
    source = inspect.getsource(app.render_sidebar)

    assert "st.pills" not in source
    assert "selection_mode=\"single\"" not in source
    assert "selection_mode='single'" not in source
    assert "sidebar_expanded_modules" in source
    assert "nav_module_toggle_" in source
    assert 'button_type = "primary" if (is_active_module or is_expanded) else "secondary"' in source
    assert 'item_type = "primary" if current == item else "secondary"' in source
    assert "_render_ui_font_size_control()" in source
    assert source.index("_render_ui_font_size_control()") < source.index("sidebar-note")


def test_global_font_size_control_modes_and_standard_baseline():
    assert app.UI_FONT_SIZE_SESSION_KEY == "ui_font_size_mode"
    assert app.UI_FONT_SIZE_QUERY_KEY == "ui_font"
    assert app.UI_FONT_SIZE_DEFAULT_MODE == "较大"
    assert app.UI_FONT_SIZE_MODES == {"标准": 1.0, "较大": 1.12, "大号": 1.25}
    assert app._normalize_ui_font_size_mode(None) == "较大"
    assert app._normalize_ui_font_size_mode("未知") == "较大"
    assert app._normalize_ui_font_size_mode("标准") == "标准"
    assert app._ui_font_size_scale("较大") == 1.12
    assert app._ui_font_size_scale("大号") == 1.25

    standard_css = app._render_ui_font_size_css("标准")
    larger_css = app._render_ui_font_size_css("较大")
    large_css = app._render_ui_font_size_css("大号")

    assert "--ui-font-scale: 1;" in standard_css
    assert "font-size:" not in standard_css
    assert "--ui-font-scale: 1.12;" in larger_css
    assert "--ui-font-scale: 1.25;" in large_css
    assert "--ui-font-table:" in larger_css
    assert "--ui-font-table-head:" in larger_css
    assert "--ui-font-caption:" in larger_css
    assert "--ui-font-chip:" in larger_css
    assert "zoom" not in larger_css
    assert "transform:" not in larger_css
    assert "section[data-testid=\"stSidebar\"]" in larger_css
    assert ".page-header" in larger_css
    assert ".home-top-kpi-grid .bi-kpi-value" in larger_css
    assert ".bi-kpi-grid:not(.home-top-kpi-grid) .bi-kpi-value" in larger_css
    assert "calc(1.42rem * var(--ui-font-scale))" in larger_css
    assert ".home-top-kpi-grid .bi-kpi-value,\n    .bi-kpi-value" not in larger_css
    assert ".home-top-kpi-grid .bi-kpi-label,\n    .bi-kpi-label" not in larger_css
    assert ".home-card-group-grid" in larger_css
    assert ".home-detail-modal" in larger_css
    assert ".home-detail-table th" in larger_css
    assert ".budget-comparison-table th" in larger_css
    assert ".budget-comparison-table td" in larger_css
    assert ".budget-drill-table th" in larger_css
    assert ".budget-drill-table td" in larger_css
    assert ".budget-status-ok" in larger_css
    assert ".budget-bridge-note" in larger_css
    assert ".operating-summary-sticky-scroll table" in larger_css
    assert ".profit-original-table" in larger_css
    assert ".income-statement-table th" in larger_css
    assert ".funds-warning-table" in larger_css
    assert ".funds-warning-card-value" in larger_css
    assert ".picture-brief-table" in larger_css
    assert ".picture-brief-template-skin .template-sheet" in larger_css
    assert ".picture-brief-kpi .value" in larger_css
    assert ".stApp [data-baseweb=\"select\"]" in larger_css
    assert ".stApp [data-baseweb=\"tab\"]" in larger_css
    assert 'font-size: min(calc(0.76rem * var(--ui-font-scale)), 0.80rem)' in larger_css


def test_sidebar_font_size_control_keeps_text_readable_on_dark_sidebar():
    css = app.PAGE_CSS
    control_start = css.index('[class*="st-key-ui_font_size_mode"] {')
    control_end = css.index(".bi-section-grid", control_start)
    control_css = css[control_start:control_end]

    assert "#d7e3f1" in control_css
    assert "#ffffff" in control_css
    assert "label:has(input:checked)" in control_css
    assert "background: #2563eb" in control_css
    assert "label:has(input:focus-visible)" in control_css
    assert "outline: 2px solid #93c5fd" in control_css
    assert "label:hover p" in control_css
    assert "overflow: visible" in control_css
    assert "st-key-ui_font_size_mode" in control_css


def test_global_font_size_query_links_preserve_nonstandard_mode():
    app.st.session_state[app.UI_FONT_SIZE_SESSION_KEY] = "大号"

    href = app._app_query_href({"drill_metric": "revenue"})
    close_href = app._app_query_href()
    sort_href, _, _ = app._metric_drilldown_sort_href("revenue", "公司", None, None)

    assert href.startswith("?ui_font=")
    assert "drill_metric=revenue" in href
    assert close_href.startswith("?ui_font=")
    assert "drill_metric=revenue" in sort_href
    assert "drill_sort=%E5%85%AC%E5%8F%B8" in sort_href
    assert "drill_order=asc" in sort_href

    app.st.session_state[app.UI_FONT_SIZE_SESSION_KEY] = "标准"
    assert app._app_query_href({"drill_metric": "revenue"}).startswith("?ui_font=")
    assert "drill_metric=revenue" in app._app_query_href({"drill_metric": "revenue"})
    assert app._app_query_href() == "?ui_font=%E6%A0%87%E5%87%86"

    app.st.session_state[app.UI_FONT_SIZE_SESSION_KEY] = app.UI_FONT_SIZE_DEFAULT_MODE
    assert app._app_query_href({"drill_metric": "revenue"}) == "?drill_metric=revenue"
    assert app._app_query_href() == "?"


def test_global_font_size_control_does_not_mutate_navigation_state():
    source = inspect.getsource(app._render_ui_font_size_control)
    main_source = inspect.getsource(app.main)
    grid_source = inspect.getsource(app._render_bi_kpi_grid)

    assert "st.radio" in source
    assert "horizontal=True" in source
    assert "label_visibility=\"collapsed\"" in source
    assert app.UI_FONT_SIZE_SESSION_KEY in source
    assert "_sync_ui_font_size_query_param" in source
    assert "nav_choice" not in source
    assert "sidebar_expanded_modules" not in source
    assert "nav_module" not in source
    assert "_app_query_href" in grid_source
    assert "st.markdown(_render_ui_font_size_css(_current_ui_font_size_mode()), unsafe_allow_html=True)" in main_source
    assert main_source.index("_render_ui_font_size_css") < main_source.index("render_sidebar")


def test_base_settings_entries_use_render_base_settings_and_default_tab():
    render_source = inspect.getsource(app.render_sidebar)
    base_source = inspect.getsource(app.render_base_settings)
    page_map_source = inspect.getsource(app.main)

    assert "base_settings_active_tab" in render_source
    assert "base_settings_active_tab" in base_source
    assert "default=active_tab" in base_source
    assert 'key=f"base_settings_tabs_{active_tab}"' in base_source
    for key in BASE_SETTINGS_KEYS:
        assert f'"{key}": render_base_settings' in page_map_source


def test_picture_brief_sidebar_click_updates_page_before_dispatch():
    render_source = inspect.getsource(app.render_sidebar)
    page_map_source = inspect.getsource(app.main)

    assert '"多维图片简报": render_multi_picture_brief' in page_map_source
    assert "on_click=_set_sidebar_page" in render_source
    assert "args=(item, page_module.get(item, module_name))" in render_source
    assert "page_slot = st.empty()" in page_map_source
    assert '"多维图片简报": "图片简报"' in inspect.getsource(app)


def test_funds_warning_entry_dispatches_to_funds_warning_page():
    page_map_source = inspect.getsource(app.main)

    assert app.NAV_LABELS["资金预警"] == "资金预警"
    assert '"资金预警": render_funds_warning' in page_map_source
    assert app._sidebar_page_module_map()["资金预警"] == "经营中心"


def test_no_single_module_pills_in_sidebar_source():
    source = inspect.getsource(app.render_sidebar)

    assert "selection_mode=\"single\"" not in source
    assert "selection_mode='single'" not in source


def test_sidebar_css_uses_larger_heavier_navigation_text():
    css = app.PAGE_CSS

    assert "[class*=\"st-key-nav_module_toggle_\"] button" in css
    assert "font-size: 1rem !important;" in css
    assert "font-weight: 800 !important;" in css
    assert "[class*=\"st-key-nav_\"]:not([class*=\"st-key-nav_module_toggle_\"]) button" in css
    assert "font-size: 0.92rem !important;" in css
    assert "font-weight: 680 !important;" in css
    assert ".nav-section-title" in css
    assert "font-size: 0.78rem !important;" in css
    assert "font-weight: 700 !important;" in css


def test_startup_docs_do_not_hardcode_8501_for_sidebar_scope():
    paths = [
        Path("README.md"),
        Path("启动finance_dw-后台运行.sh"),
        Path("启动 finance_dw.command"),
    ]
    existing_text = "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())

    assert "8501" not in existing_text
    assert "8502" in existing_text
