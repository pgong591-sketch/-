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
