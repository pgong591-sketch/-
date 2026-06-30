import inspect

import pandas as pd
import pytest

import app
from src import operating_summary
from src.operating_summary import build_empty_operating_summary_rows, build_operating_summary_rows


def _row(rows, name):
    return next(item for item in rows if item["费用科目"] == name)


def test_operating_summary_collects_income_cost_expense_rules():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "收入合计", 2000.0),
            ("001", "测试校区", "成本费用合计", 1000.0),
            ("001", "测试校区", "学生福利", 40.0),
            ("001", "测试校区", "教学用具", 60.0),
            ("001", "测试校区", "房租", 120.0),
            ("001", "测试校区", "水电费", 80.0),
            ("001", "测试校区", "工资", 300.0),
            ("001", "测试校区", "社保费", 100.0),
            ("001", "测试校区", "折旧费", 50.0),
            ("001", "测试校区", "待摊费", 30.0),
            ("001", "测试校区", "管理费服务费", 70.0),
            ("001", "测试校区", "财务费用", 20.0),
        ],
        columns=["company_code", "company_name", "source_item_name", "current_amount"],
    )
    previous = pd.DataFrame(
        [
            ("001", "测试校区", "收入合计", 1600.0),
            ("001", "测试校区", "成本费用合计", 800.0),
            ("001", "测试校区", "学生福利", 20.0),
            ("001", "测试校区", "教学用具", 30.0),
            ("001", "测试校区", "房租", 60.0),
            ("001", "测试校区", "水电费", 40.0),
            ("001", "测试校区", "工资", 200.0),
            ("001", "测试校区", "社保费", 50.0),
            ("001", "测试校区", "折旧费", 30.0),
            ("001", "测试校区", "待摊费", 10.0),
            ("001", "测试校区", "管理费服务费", 70.0),
            ("001", "测试校区", "财务费用", 10.0),
        ],
        columns=["company_code", "company_name", "source_item_name", "current_amount"],
    )

    rows = build_operating_summary_rows(current, previous)

    assert _row(rows, "学生福利及教具")["合计"] == 100.0
    assert _row(rows, "房租水电")["合计"] == 200.0
    assert _row(rows, "人工")["合计"] == 400.0
    assert _row(rows, "折旧及摊销")["合计"] == 80.0
    assert _row(rows, "其他")["合计"] == 130.0
    assert _row(rows, "净利润")["合计"] == 1000.0
    assert _row(rows, "实际成本")["合计"] == 920.0
    assert _row(rows, "净利润（不含折旧与摊销）")["合计"] == 1080.0
    assert _row(rows, "学生福利及教具")["占费用比"] == 0.1
    assert _row(rows, "学生福利及教具")["占收入比"] == 0.05
    assert _row(rows, "收入合计")["占收入比"] == 1.0
    assert round(_row(rows, "成本费用合计")["环比"], 4) == 0.25


def test_operating_summary_expands_company_tree_without_duplicates(monkeypatch):
    def fake_company_list(code):
        return {
            "GROUP": ["GROUP", "001", "002"],
            "001": ["001"],
        }[code]

    monkeypatch.setattr(operating_summary, "get_company_list_for_summary", fake_company_list)

    assert operating_summary._expand_company_codes(["GROUP", "001"]) == ["GROUP", "001", "002"]


def test_operating_summary_prefers_operating_totals_over_summary_duplicates():
    current = pd.DataFrame(
        [
            ("1011801", "少年宫", "SUMMARY_002_收入合计", "收入合计", 255342.80),
            ("1011801", "少年宫", "OPERATING_012_收入合计", "收入合计", 255342.80),
            ("1011801", "少年宫", "SUMMARY_001_成本费用合计", "成本费用合计", 412256.39),
            ("1011801", "少年宫", "OPERATING_011_成本费用合计", "成本费用合计", 412256.39),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == pytest.approx(255342.80)
    assert _row(rows, "成本费用合计")["合计"] == pytest.approx(412256.39)
    assert _row(rows, "净利润")["合计"] == pytest.approx(-156913.59)


def test_operating_summary_uses_ytd_amount_for_annual_totals_and_ratios():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "DETAIL_001", "学生福利", 40.0, 140.0),
            ("001", "测试校区", "DETAIL_002", "教学用具", 60.0, 160.0),
            ("001", "测试校区", "OPERATING_008_折旧及摊销", "折旧及摊销", 50.0, 120.0),
            ("001", "测试校区", "OPERATING_010_其他", "其他", 80.0, 200.0),
            ("001", "测试校区", "OPERATING_011_成本费用合计", "成本费用合计", 500.0, 900.0),
            ("001", "测试校区", "OPERATING_012_收入合计", "收入合计", 1000.0, 2000.0),
            ("001", "测试校区", "OPERATING_013_净利润", "净利润", 500.0, 1100.0),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "学生福利及教具")["合计"] == 100.0
    assert _row(rows, "学生福利及教具")["2026合计"] == 300.0
    assert _row(rows, "学生福利及教具")["占费用比"] == pytest.approx(0.2)
    assert _row(rows, "学生福利及教具")["年度占费用比"] == pytest.approx(300.0 / 900.0)
    assert _row(rows, "收入合计")["合计"] == 1000.0
    assert _row(rows, "收入合计")["2026合计"] == 2000.0
    assert _row(rows, "收入合计")["年度占收入比"] == 1.0
    assert _row(rows, "成本费用合计")["合计"] == 500.0
    assert _row(rows, "成本费用合计")["2026合计"] == 900.0
    assert _row(rows, "净利润")["合计"] == 500.0
    assert _row(rows, "净利润")["2026合计"] == 1100.0
    assert _row(rows, "折旧及摊销")["合计"] == 50.0
    assert _row(rows, "折旧及摊销")["2026合计"] == 120.0
    assert _row(rows, "其他")["合计"] == 80.0
    assert _row(rows, "其他")["2026合计"] == 200.0


def test_operating_summary_blank_ytd_amount_falls_back_to_current_amount():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "OPERATING_012_收入合计", "收入合计", 100.0, ""),
            ("001", "测试校区", "OPERATING_011_成本费用合计", "成本费用合计", 40.0, "   "),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["2026合计"] == 100.0
    assert _row(rows, "成本费用合计")["2026合计"] == 40.0
    assert _row(rows, "净利润")["2026合计"] == 60.0


def test_multi_operating_original_rows_use_ytd_source_detail(monkeypatch):
    current = pd.DataFrame(
        [
            ("1011801", "少年宫", "OPERATING_012_收入合计", "收入合计", 255342.80, 703698.77),
            ("1011801", "少年宫", "OPERATING_011_成本费用合计", "成本费用合计", 412256.39, 1147483.31),
            ("1011801", "少年宫", "OPERATING_013_净利润", "净利润", -156913.59, -443784.54),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount"],
    )

    monkeypatch.setattr(app, "get_operating_summary_source_detail", lambda period, company_codes: current if period == "202603" else pd.DataFrame())
    monkeypatch.setattr(app, "apply_internal_management_fee_elimination", lambda source_df, company_codes: source_df)

    rows = app._build_operating_original_rows_for_scope("202603", None, ["1011801"])

    assert _row(rows, "收入合计")["合计"] == pytest.approx(255342.80)
    assert _row(rows, "收入合计")["2026合计"] == pytest.approx(703698.77)
    assert _row(rows, "成本费用合计")["2026合计"] == pytest.approx(1147483.31)
    assert _row(rows, "净利润")["2026合计"] == pytest.approx(-443784.54)


def test_render_multi_operating_summary_passes_operating_rows(monkeypatch):
    class DummyContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    expected_rows = [
        {
            "费用科目": "收入合计",
            "合计": 255342.80,
            "2026合计": 703698.77,
        }
    ]
    captured = {}

    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "tabs", lambda labels: [DummyContext() for _ in labels])
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "columns", lambda *args, **kwargs: [DummyContext(), DummyContext()])
    monkeypatch.setattr(app, "get_dashboard_periods", lambda: ["202603", "202602"])
    monkeypatch.setattr(app, "_get_business_group_options", lambda: ["不限"])
    monkeypatch.setattr(app, "_render_workspace_filter_bar", lambda **kwargs: {"period": "202603"})
    monkeypatch.setattr(app, "_resolve_filter_company_codes", lambda filters: ["1011801"])
    monkeypatch.setattr(app, "_workspace_scope_label", lambda filters: "少年宫")
    monkeypatch.setattr(app, "get_operating_summary", lambda period, company_codes=None: pd.DataFrame())
    monkeypatch.setattr(app, "get_multidim_income_statement", lambda period, company_codes=None: pd.DataFrame())
    monkeypatch.setattr(app, "_operating_company_metrics", lambda detail_df: pd.DataFrame())
    monkeypatch.setattr(app, "_operating_period_series", lambda periods, period, company_codes: pd.DataFrame())
    monkeypatch.setattr(app, "_operating_structure", lambda detail_df: pd.DataFrame())
    monkeypatch.setattr(app, "_operating_alerts", lambda summary_df, previous_summary_df: [])
    monkeypatch.setattr(app, "_build_operating_original_rows_for_scope", lambda period, previous_period, company_codes: expected_rows)
    monkeypatch.setattr(app, "_render_operating_dashboard_design", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_bi_kpi_grid", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_operating_company_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_fixed_template_sheet", lambda *args, **kwargs: None)

    def fake_original_design(period, scope_label, company_codes, detail_df, previous_detail_df, filters=None, operating_rows=None):
        captured["operating_rows"] = operating_rows

    monkeypatch.setattr(app, "_render_operating_original_design", fake_original_design)

    app.render_multi_operating_summary()

    assert captured["operating_rows"] is expected_rows
    assert captured["operating_rows"][0]["2026合计"] != captured["operating_rows"][0]["合计"]


def test_operating_summary_uses_summary_totals_when_operating_missing():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "SUMMARY_002_收入合计", "收入合计", 3000.0),
            ("001", "测试校区", "SUMMARY_001_成本费用合计", "成本费用合计", 1200.0),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 3000.0
    assert _row(rows, "成本费用合计")["合计"] == 1200.0
    assert _row(rows, "净利润")["合计"] == 1800.0


def test_operating_summary_deduplicates_duplicate_operating_totals_by_last_row():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "OPERATING_012_收入合计", "收入合计", 100.0, 1000.0, 10),
            ("001", "测试校区", "OPERATING_012_收入合计", "收入合计", 120.0, 1300.0, 20),
            ("001", "测试校区", "OPERATING_011_成本费用合计", "成本费用合计", 40.0, 400.0, 30),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount", "source_row"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 120.0
    assert _row(rows, "收入合计")["2026合计"] == 1300.0
    assert _row(rows, "成本费用合计")["合计"] == 40.0
    assert _row(rows, "成本费用合计")["2026合计"] == 400.0
    assert _row(rows, "净利润")["合计"] == 80.0
    assert _row(rows, "净利润")["2026合计"] == 900.0


def test_operating_summary_deduplicates_duplicate_summary_totals_by_input_order():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "SUMMARY_002_收入合计", "收入合计", 100.0),
            ("001", "测试校区", "SUMMARY_002_收入合计", "收入合计", 130.0),
            ("001", "测试校区", "SUMMARY_001_成本费用合计", "成本费用合计", 50.0),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 130.0
    assert _row(rows, "成本费用合计")["合计"] == 50.0
    assert _row(rows, "净利润")["合计"] == 80.0


def test_operating_summary_deduplicates_duplicate_totals_per_company():
    current = pd.DataFrame(
        [
            ("001", "A校区", "OPERATING_012_收入合计", "收入合计", 100.0, 1),
            ("001", "A校区", "OPERATING_012_收入合计", "收入合计", 120.0, 2),
            ("001", "A校区", "OPERATING_011_成本费用合计", "成本费用合计", 40.0, 3),
            ("002", "B校区", "OPERATING_012_收入合计", "收入合计", 200.0, 1),
            ("002", "B校区", "OPERATING_012_收入合计", "收入合计", 250.0, 2),
            ("002", "B校区", "OPERATING_011_成本费用合计", "成本费用合计", 90.0, 3),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "row_id"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 370.0
    assert _row(rows, "成本费用合计")["合计"] == 130.0
    assert _row(rows, "净利润")["合计"] == 240.0


def test_operating_summary_deduplicates_operating_total_aliases_by_canonical_item():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "OPERATING_012_收入合计", "收入合计", 100.0, 10),
            ("001", "测试校区", "OPERATING_012_营业收入", "营业收入", 100.0, 20),
            ("001", "测试校区", "OPERATING_011_成本费用合计", "成本费用合计", 40.0, 30),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "source_row"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 100.0
    assert _row(rows, "成本费用合计")["合计"] == 40.0
    assert _row(rows, "净利润")["合计"] == 60.0


def test_operating_summary_deduplicates_summary_total_aliases_by_canonical_item():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "SUMMARY_002_收入合计", "收入合计", 100.0, 1),
            ("001", "测试校区", "SUMMARY_002_营业收入", "营业收入", 130.0, 2),
            ("001", "测试校区", "SUMMARY_001_成本费用合计", "成本费用合计", 50.0, 3),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "row_id"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "收入合计")["合计"] == 130.0
    assert _row(rows, "成本费用合计")["合计"] == 50.0
    assert _row(rows, "净利润")["合计"] == 80.0


def test_operating_summary_deduplicates_depreciation_aliases_by_canonical_item():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "OPERATING_008_折旧及摊销", "折旧及摊销", 10.0, 1),
            ("001", "测试校区", "OPERATING_008_折旧与待摊费用合计", "折旧与待摊费用合计", 12.0, 2),
            ("001", "测试校区", "OPERATING_011_成本费用合计", "成本费用合计", 40.0, 3),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "source_row"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "折旧及摊销")["合计"] == 12.0
    assert _row(rows, "成本费用合计")["合计"] == 40.0
    assert _row(rows, "实际成本")["合计"] == 28.0


def test_operating_summary_cost_total_falls_back_to_real_details_only():
    current = pd.DataFrame(
        [
            ("001", "测试校区", "DETAIL_001", "学生福利", 40.0),
            ("001", "测试校区", "DETAIL_002", "教学用具", 60.0),
            ("001", "测试校区", "SUMMARY_折旧费", "折旧费", 50.0),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount"],
    )

    rows = build_operating_summary_rows(current)

    assert _row(rows, "学生福利及教具")["合计"] == 100.0
    assert _row(rows, "折旧及摊销")["合计"] == 0.0
    assert _row(rows, "成本费用合计")["合计"] == 100.0
    assert _row(rows, "其他")["合计"] == 0.0


def test_empty_operating_summary_keeps_table_structure():
    rows = build_empty_operating_summary_rows()

    assert [row["费用科目"] for row in rows[:3]] == ["学生福利及教具", "房租水电", "人工"]
    assert rows[-1]["费用科目"] == "净利润（不含折旧与摊销）"
    assert all(row["合计"] == 0 for row in rows)
    assert all(row["占费用比"] is None for row in rows)


def test_profit_original_display_model_uses_version_6_item_names():
    source_rows = build_empty_operating_summary_rows()

    display_rows = app._profit_original_display_model_rows(source_rows)

    assert [row["display_item_name"] for row in display_rows] == [
        "学生福利及教具",
        "房租水电",
        "人工",
        "税金",
        "销售费用",
        "办公",
        "交际费",
        "折旧及摊销",
        "其他",
        "成本费用合计",
        "收入总额",
        "净利润",
        "净利润（不含计提折旧与摊销）",
    ]
    assert len(display_rows) == 13


def test_profit_original_table_html_is_fixed_8_columns_without_colgroup():
    row = app._profit_original_display_model_rows([
        {
            "费用科目": "收入合计",
            "合计": 100.0,
            "2026合计": 300.0,
            "占费用比": None,
            "占收入比": 1.0,
            "备注": "来自收入成本费用明细表",
            "row_type": "summary",
            "is_profit": False,
            "is_total": True,
        }
    ])[10]

    header_html = app._profit_original_table_header_html()
    row_html = app._profit_original_table_row_html(row, ["001"])
    css = app._operating_design_css()

    assert "<colgroup>" not in header_html
    assert header_html.count("<th>") == 8
    assert row_html.count("<td") == 8
    assert "<td>收入总额</td>" in row_html
    assert "来自收入成本费用明细表" in row_html
    assert ".profit-original-table th:nth-child(1)" in css
    assert ".profit-original-table th:nth-child(8)" in css
    expected_widths = [18, 14, 9, 9, 15, 9, 9, 17]
    for idx, width in enumerate(expected_widths, start=1):
        assert (
            f".profit-original-table th:nth-child({idx}),"
            f".profit-original-table td:nth-child({idx})"
            f"{{width:{width}%;}}"
        ) in css
    assert sum(expected_widths) == 100


def test_profit_original_table_html_uses_ytd_total_column_value():
    row = app._profit_original_display_model_rows([
        {
            "费用科目": "收入合计",
            "合计": 255342.80,
            "2026合计": 703698.77,
            "占费用比": None,
            "占收入比": 1.0,
            "年度占费用比": None,
            "年度占收入比": 1.0,
            "备注": "来自收入成本费用明细表",
            "row_type": "summary",
            "is_profit": False,
            "is_total": True,
        }
    ])[10]

    row_html = app._profit_original_table_row_html(row, ["1011801"])

    assert "255,342.80" in row_html
    assert "703,698.77" in row_html
    assert row_html.index("255,342.80") < row_html.index("703,698.77")


def test_legacy_original_table_rows_do_not_fake_ytd_totals():
    detail_df = pd.DataFrame(
        [
            ("收入合计", 100.0),
            ("成本费用合计", 40.0),
            ("净利润", 60.0),
        ],
        columns=["项目", "合计"],
    )

    rows = app._profit_original_table_rows(detail_df, pd.DataFrame())

    assert rows
    assert all(row.get("2026合计") is None for row in rows)


def test_legacy_operating_table_rows_do_not_fake_ytd_totals():
    detail_df = pd.DataFrame(
        [
            ("一、营业收入", 100.0),
            ("减：营业成本", 40.0),
            ("净利润", 60.0),
        ],
        columns=["项目", "合计"],
    )

    rows = app._operating_table_rows(detail_df, pd.DataFrame())

    assert rows
    assert all(row.get("2026合计") is None for row in rows)


def test_operating_original_design_no_longer_uses_legacy_table_fallback():
    source = inspect.getsource(app._render_operating_original_design)

    assert "_profit_original_table_rows" not in source
    assert "build_empty_operating_summary_rows()" in source


def test_operating_summary_month_filter_displays_chinese_month_without_changing_value():
    formatter = app._filter_month_format_func("profit_original")

    assert formatter is app._filter_month_display_label
    assert formatter("01") == "1月"
    assert formatter("03") == "3月"
    assert formatter("12") == "12月"
    assert formatter("不限") == "不限"
    assert app._filter_month_format_func("expense_subject") is None
