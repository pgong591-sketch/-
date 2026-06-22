import inspect

import app


def test_sidebar_has_four_top_level_modules_and_base_settings_entry():
    assert list(app.NAV_MODULE_SECTIONS) == ["经营中心", "数据中心", "财务中心", "基础设置"]
    assert app.NAV_MODULE_SECTIONS["基础设置"] == {"主数据与口径": ["基础设置"]}
    assert app._sidebar_page_module_map()["基础设置"] == "基础设置"


def test_sidebar_expanded_state_keeps_multiple_modules_open():
    expanded = app._sidebar_expanded_state(
        "基础设置",
        {"经营中心": True, "数据中心": False, "基础设置": True},
    )

    assert expanded["经营中心"] is True
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
    expanded = app._sidebar_expanded_state("基础设置", {})

    assert expanded["基础设置"] is True
    assert expanded["经营中心"] is False


def test_sidebar_render_uses_buttons_not_single_select_pills():
    source = inspect.getsource(app.render_sidebar)

    assert "st.pills" not in source
    assert "nav_module_toggle_" in source
    assert 'button_type = "primary" if is_active_module else "secondary"' in source
    assert 'item_type = "primary" if current == item else "secondary"' in source
