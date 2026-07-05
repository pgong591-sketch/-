from pathlib import Path
import inspect

import app
import pandas as pd
import pytest
from openpyxl import Workbook
from openpyxl.styles import Border, Font, PatternFill, Side

from src.template_workbook import (
    TemplateWorkbookError,
    _contrast_ratio,
    _readable_text_color,
    clear_template_workbook_caches,
    get_template_workbook_path,
    load_template_sheet,
    load_template_sheet_frame,
)


def _build_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "图片简报"
    ws["A1"] = "标题"
    ws["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    ws["A1"].font = Font(color="FFFFFF", bold=True, size=16)
    ws["A2"] = "=1+1"
    ws["A3"] = "月报内容"
    ws["B3"] = "累计内容"
    ws["A4"] = 0.125
    ws["A4"].number_format = "0.0%"
    ws["B4"] = 1234.56
    ws["B4"].number_format = "#,##0.00"
    ws["A4"].border = Border(bottom=Side(style="thick", color="FF0000"))
    ws.merge_cells("A1:B1")

    income = wb.create_sheet("损益表")
    income["A1"] = "项目"
    income["B1"] = "本月数"
    income["A2"] = "营业收入"
    income["B2"] = 100

    summary = wb.create_sheet("经营汇总表")
    summary["A1"] = "项目"
    summary["B1"] = "金额"
    summary["A2"] = "净利润"
    summary["B2"] = 30
    summary["B2"].font = Font(color="FFFFFF")
    summary["B2"].fill = PatternFill("solid", fgColor="FFFFFF")
    summary["B3"] = "23.2%"
    summary["B3"].font = Font(color="FFFFFF")
    summary["B3"].fill = PatternFill("solid", fgColor="FFFFFF")
    wb.save(path)


def test_template_workbook_uses_configured_file_without_transforming_sheet(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    assert get_template_workbook_path() == template_path

    frame = load_template_sheet_frame("损益表")
    assert list(frame.columns) == ["A", "B"]
    assert frame.loc[1, "A"] == "项目"
    assert frame.loc[2, "A"] == "营业收入"
    assert frame.loc[2, "B"] == 100

    formatted = load_template_sheet_frame("图片简报", formatted=True)
    assert formatted.loc[4, "A"] == "12.5%"


def test_template_workbook_frame_cache_invalidates_when_file_changes(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))
    clear_template_workbook_caches()

    assert load_template_sheet_frame("损益表").loc[2, "B"] == 100

    wb = Workbook()
    ws = wb.active
    ws.title = "损益表"
    ws["A1"] = "项目"
    ws["B1"] = "本月数"
    ws["A2"] = "营业收入"
    ws["B2"] = 200
    wb.create_sheet("图片简报")
    wb.create_sheet("经营汇总表")
    wb.save(template_path)
    template_path.touch()

    assert load_template_sheet_frame("损益表").loc[2, "B"] == 200


def test_template_workbook_preview_preserves_merges_and_formula_text(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    sheet = load_template_sheet("图片简报")

    assert sheet.sheet_name == "图片简报"
    assert sheet.row_count == 4
    assert 'colspan="2"' in sheet.html
    assert "标题" in sheet.html
    assert "=1+1" in sheet.html
    assert "background-color:#1F4E78" in sheet.html
    assert "color:#FFFFFF" in sheet.html
    assert "font-weight:700" in sheet.html
    assert "12.5%" in sheet.html
    assert "1,234.56" in sheet.html
    assert 'class="numeric-cell"' in sheet.html
    assert "border-bottom:3px solid #FF0000" in sheet.html


def test_template_workbook_can_crop_picture_brief_columns(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    sheet = load_template_sheet("图片简报", min_col=1, max_col=1)

    assert "月报内容" in sheet.html
    assert "累计内容" not in sheet.html
    assert sheet.column_count == 1


def test_template_workbook_reports_missing_sheet(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    with pytest.raises(TemplateWorkbookError):
        load_template_sheet("不存在")


def test_readable_text_color_keeps_sufficient_contrast():
    assert _contrast_ratio("#111827", "#ffffff") >= 4.5
    assert _readable_text_color("#111827", "#ffffff") == "#111827"
    assert _readable_text_color("#ffffff", "#1F4E78") == "#ffffff"


def test_readable_text_color_fixes_low_contrast_on_light_background():
    assert _readable_text_color("#ffffff", "#ffffff", is_numeric=True) == "#111827"
    assert _readable_text_color("#ff0000", "#ffffff", is_numeric=True) == "#111827"
    assert _readable_text_color("#f8fafc", "#ffffff") == "#111827"


def test_readable_text_color_fixes_low_contrast_on_dark_background():
    assert _readable_text_color("#111827", "#000000") == "#ffffff"
    assert _readable_text_color(None, "#000000") == "#ffffff"


def test_numeric_template_cell_uses_readable_color(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    sheet = load_template_sheet("经营汇总表")

    assert "30" in sheet.html
    assert "23.2%" in sheet.html
    assert 'class="numeric-cell"' in sheet.html
    assert "color:#111827!important" in sheet.html


def test_template_workbook_marks_negative_cells_and_total_rows(tmp_path, monkeypatch):
    wb = Workbook()
    ws = wb.active
    ws.title = "图片简报"
    ws["A1"] = "项目"
    ws["B1"] = "金额"
    ws["A2"] = "合计"
    ws["B2"] = -123.45
    ws["B2"].number_format = "#,##0.00"
    ws["A3"] = "类别"
    ws["B3"] = "素质中心"
    ws["A4"] = "净利润"
    ws["B4"] = -10.0
    template_path = tmp_path / "报表模板.xlsx"
    wb.save(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    sheet = load_template_sheet("图片简报")

    assert 'class="template-total-row"' in sheet.html
    assert "template-header-row" in sheet.html
    assert "template-risk-row" in sheet.html
    assert "numeric-cell negative-cell" in sheet.html


def test_picture_brief_uses_financial_table_skin_without_changing_content(tmp_path, monkeypatch):
    template_path = tmp_path / "报表模板.xlsx"
    _build_template(template_path)
    monkeypatch.setenv("FINANCE_DW_REPORT_TEMPLATE_PATH", str(template_path))

    sheet = load_template_sheet("图片简报", min_col=1, max_col=1)
    html = app._picture_brief_template_skin_html(sheet.html)

    assert "picture-brief-template-skin" in html
    assert "border-collapse: collapse" in html
    assert "box-shadow:" in html
    assert "template-header-row" in html
    assert "template-section-row" in html
    assert "template-total-row" in html
    assert "template-risk-row" in html
    assert "td.numeric-cell" in html
    assert "td.negative-cell" in html
    assert "月报内容" in html
    assert "累计内容" not in html


def test_picture_brief_page_keeps_original_switch_and_has_no_company_filter():
    source = inspect.getsource(app.render_multi_picture_brief)

    assert '["月报", "本年累计"]' in source
    assert "_picture_brief_load_grid" in source
    assert "_picture_brief_table_html" in source
    assert "_render_picture_brief_trends" not in source
    assert "趋势图" not in source
    assert "经营单位" not in source


def test_picture_brief_dashboard_parses_kpis_and_sections():
    grid = pd.DataFrame(
        [
            ["2026年3月集团经营月报（简报）", "", "", "", ""],
            ["集团经营情况", "", "", "", ""],
            ["本月经营收入", "2,095", "经营净利润", "245", ""],
            ["净利率", "12%", "资金余额", "13,763", ""],
            ["预收账款", "8,715", "资金周转率", "7.1", ""],
            ["", "", "", "", ""],
            ["素质中心报告", "", "", "", ""],
            ["类别", "素质中心", "合并统计", "", "收入占比"],
            ["收入", "1,659", "1,807", "", ""],
            ["净利润", "443", "294", "", ""],
            ["其他模块报告", "", "", "", ""],
            ["类别", "学校", "幼儿园", "", ""],
            ["净利润", "14", "-9", "", ""],
            ["对外投资情况", "", "", "", ""],
            ["类别", "深圳卓越", "中科心研", "", "凤来置业"],
            ["收入", "205", "8", "", "98"],
            ["各校区具体情况", "", "", "", ""],
            ["校区", "收入", "净利润", "净利率", "校区"],
            ["莞小", "147", "38", "26%", "东泰"],
            ["月份", "3", "", "", ""],
            ["@所有人 各位,", "", "", "", ""],
            ["第1个表为3月简报，本月集团收入2095。", "", "", "", ""],
        ]
    )

    pairs = dict(app._picture_brief_metric_pairs(grid.iloc[2].tolist()))
    quality_rows = app._picture_brief_section_table(grid, "素质中心报告")
    investment_rows = app._picture_brief_section_table(grid, "对外投资情况")
    campus_rows = app._picture_brief_section_table(grid, "各校区具体情况")
    other_html = app._picture_brief_table_html("其他模块报告", app._picture_brief_section_table(grid, "其他模块报告"))
    note_html = app._picture_brief_auto_note_html(grid, grid)

    assert pairs["本月经营收入"] == "2,095"
    assert pairs["经营净利润"] == "245"
    assert quality_rows[0] == ["类别", "素质中心", "合并统计", "收入占比"]
    assert investment_rows[0] == ["类别", "深圳卓越", "中科心研", "凤来置业"]
    assert all("@所有人" not in "".join(row) for row in campus_rows)
    assert all("第1个表" not in "".join(row) for row in campus_rows)
    assert all(row[0] != "月份" for row in campus_rows)
    assert "经营简报说明" in note_html
    assert "集团收入 2,095" in note_html
    assert "@所有人" not in note_html
    assert "picture-brief-header-row" in other_html
    assert "picture-brief-risk-row" in other_html
    assert "picture-brief-negative" in other_html


def _picture_brief_pl_fixture() -> pd.DataFrame:
    rows = []
    id_counter = 1
    values = {
        "1010101": (10000, 30000, 1000, 3000, 2000, 6000, 300, 900, 5000, 15000),
        "1010102": (20000, 60000, 2000, 6000, 3000, 9000, 400, 1200, 8000, 24000),
        "1020401": (30000, 90000, -1000, -3000, 4000, 12000, 500, 1500, 10000, 30000),
        "10204": (40000, 120000, -2000, -6000, 5000, 15000, 600, 1800, 12000, 36000),
        "101": (50000, 150000, 10000, 30000, 6000, 18000, 700, 2100, 14000, 42000),
    }
    item_specs = [
        ("收入合计", 0, 1),
        ("净利润", 2, 3),
        ("人工", 4, 5),
        ("房租水电", 6, 7),
        ("成本费用合计", 8, 9),
    ]
    for code, metrics in values.items():
        for item_name, amount_idx, ytd_idx in item_specs:
            rows.append(
                {
                    "id": id_counter,
                    "company_code": code,
                    "item_code": f"OPERATING_{id_counter:03d}",
                    "item_name": item_name,
                    "amount": metrics[amount_idx],
                    "ytd_amount": metrics[ytd_idx],
                }
            )
            id_counter += 1
    rows.append(
        {
            "id": 999,
            "company_code": "1010101",
            "item_code": "SUMMARY_002",
            "item_name": "收入合计",
            "amount": 999999,
            "ytd_amount": 999999,
        }
    )
    return pd.DataFrame(rows)


def test_picture_brief_kpis_use_pl_detail_amount_and_ytd(monkeypatch):
    monkeypatch.setattr(app, "_picture_brief_pl_detail_rows", lambda period: _picture_brief_pl_fixture())

    month_kpis = app._picture_brief_kpis_from_pl_detail("202603", "月报")
    ytd_kpis = app._picture_brief_kpis_from_pl_detail("202603", "本年累计")

    assert [label for label, _ in month_kpis] == [
        "本月经营收入",
        "经营净利润",
        "净利率",
        "人工",
        "租金",
        "成本费用合计",
    ]
    assert [label for label, _ in ytd_kpis] == [
        "本年累计收入",
        "经营净利润",
        "净利率",
        "人工",
        "租金",
        "成本费用合计",
    ]
    assert dict(month_kpis)["本月经营收入"] == "15"
    assert dict(month_kpis)["经营净利润"] == "1"
    assert dict(month_kpis)["净利率"] == "7%"
    assert dict(month_kpis)["人工"] == "2"
    assert dict(month_kpis)["租金"] == "0"
    assert dict(ytd_kpis)["本年累计收入"] == "45"
    assert dict(ytd_kpis)["经营净利润"] == "3"
    assert dict(ytd_kpis)["人工"] == "6"


def test_picture_brief_quality_section_uses_confirmed_scopes(monkeypatch):
    monkeypatch.setattr(app, "_picture_brief_pl_detail_rows", lambda period: _picture_brief_pl_fixture())
    monkeypatch.setattr(
        app,
        "_picture_brief_company_descendants",
        lambda code, include_root=False: {
            "10101": ["1010101", "1010102"],
            "10204": ["1020401"],
        }.get(code, [code] if include_root else []),
    )

    rows = app._picture_brief_quality_section_from_pl_detail("202603", "月报")
    ytd_rows = app._picture_brief_quality_section_from_pl_detail("202603", "本年累计")

    assert rows[0] == ["类别", "素质中心", "尔遇", "尔遇管理中心", "管理中心", "合并统计", "同比增长", "收入占比"]
    assert rows[1] == ["收入", "3", "3", "4", "5", "15", "", ""]
    assert rows[2] == ["净利润", "0", "0", "0", "1", "1", "", ""]
    assert rows[4] == ["人工", "1", "0", "1", "1", "2", "", ""]
    assert rows[5] == ["租金", "0", "0", "0", "0", "0", "", ""]
    assert ytd_rows[1] == ["收入", "9", "9", "12", "15", "45", "", ""]


def test_picture_brief_operating_context_reuses_one_pl_detail_query(monkeypatch):
    calls: list[str] = []

    def fake_rows(period: str) -> pd.DataFrame:
        calls.append(period)
        return _picture_brief_pl_fixture()

    company_tree = pd.DataFrame(
        [
            {"code": "1010101", "parent_code": "10101"},
            {"code": "1010102", "parent_code": "10101"},
            {"code": "1020401", "parent_code": "10204"},
        ]
    )

    monkeypatch.setattr(app, "_picture_brief_pl_detail_rows", fake_rows)
    monkeypatch.setattr(app, "_picture_brief_db_signature", lambda: ("test.db", 1))
    monkeypatch.setattr(app, "_picture_brief_company_tree_rows_cached", lambda db_path, db_mtime: company_tree)

    context = app._picture_brief_operating_context("202603")

    assert calls == ["202603"]
    assert dict(context["month_kpis"])["本月经营收入"] == "15"
    assert dict(context["ytd_kpis"])["本年累计收入"] == "45"
    assert context["month_quality_rows"][1] == ["收入", "3", "3", "4", "5", "15", "", ""]


def test_picture_brief_kpi_html_uses_larger_colored_values():
    html = app._picture_brief_kpi_html(
        [("本月经营收入", "2,095"), ("净利率", "12%"), ("经营净利润", "-245")]
    )
    css = app._picture_brief_styles()

    assert "picture-brief-kpi-primary" in html
    assert "picture-brief-kpi-positive" in html
    assert "picture-brief-kpi-negative" in html
    assert "font-size: 30px" in css
    assert "#1d4ed8" in css
    assert "#16a34a" in css
    assert "#dc2626" in css


def test_picture_brief_styles_align_text_and_constrain_campus_columns():
    css = app._picture_brief_styles()

    assert ".picture-brief-page-title" in css
    assert "font-size: 30px;" in css
    assert "font-size: 16px;" in css
    assert "line-height: 1.42;" in css
    assert "max-width: min(100%, 1680px)" in css
    assert "grid-template-columns: repeat(6, minmax(140px, 1fr))" in css
    assert ".picture-brief-table-scroll { overflow-x: auto; width: 100%; }" in css
    assert "width: 100%;" in css
    assert "min-width: 720px;" in css
    assert "table-layout: fixed;" in css
    assert "col.picture-brief-first-col { width: 170px; }" in css
    assert "col.picture-brief-data-col { width: 138px; }" in css
    assert ".picture-brief-table td {" in css
    assert "text-align: center;" in css
    assert "overflow-wrap: anywhere;" in css
    assert "td.picture-brief-num" in css
    assert "text-align: right;" in css
    assert ".picture-brief-campus-table td:nth-child(1)" in css
    assert "min-width: 920px;" in css
    assert "max-width: none;" in css
    assert ".picture-brief-trend-grid" in css


def test_picture_brief_table_html_uses_colgroup_for_uniform_widths():
    html = app._picture_brief_table_html(
        "素质中心报告",
        [
            ["类别", "素质中心", "尔遇", "尔遇管理中心", "管理中心", "合并统计", "同比增长", "收入占比"],
            ["收入", "1,659", "135", "0", "61", "1,854", "", ""],
        ],
    )

    assert '<col class="picture-brief-first-col">' in html
    assert html.count('class="picture-brief-data-col"') == 7
    assert 'style="min-width:1136px"' in html
    assert "尔遇管理中心" in html
    assert "picture-brief-num" in html


def test_picture_brief_trend_uses_real_multi_period_data(monkeypatch):
    monkeypatch.setattr(app, "get_dashboard_periods", lambda: ["202601", "202602", "202603"])

    def fake_execute_sql(sql, params=None):
        assert "income_statement" in sql
        return pd.DataFrame(
            [
                {"period": "202601", "revenue": 100.0, "net_profit": -20.0},
                {"period": "202602", "revenue": 180.0, "net_profit": 30.0},
                {"period": "202603", "revenue": 260.0, "net_profit": 45.0},
            ]
        )

    monkeypatch.setattr(app, "execute_sql", fake_execute_sql)

    trend = app._picture_brief_trend_frame("2026", "03")

    revenue = trend["收入"].tolist()
    profit = trend["净利润"].tolist()
    assert revenue == [100.0, 180.0, 260.0]
    assert profit == [-20.0, 30.0, 45.0]
    assert trend["累计收入"].tolist() == [100.0, 280.0, 540.0]
    assert trend["净利率"].round(4).tolist() == [-0.2, 0.1667, 0.1731]
    assert len(set(revenue)) > 1


def test_picture_brief_trend_conclusions_are_generated_from_latest_period():
    trend = pd.DataFrame(
        [
            {"期间": "202602", "收入": 180.0, "累计收入": 180.0, "净利润": 30.0, "净利率": 0.1667},
            {"期间": "202603", "收入": 260.0, "累计收入": 440.0, "净利润": 45.0, "净利率": 0.1731},
        ]
    )

    conclusions = app._picture_brief_trend_conclusions(trend)

    assert "3月收入较上期上升 44.4%" in conclusions["收入趋势"]
    assert "累计收入为" in conclusions["收入趋势"]
    assert "3月净利润较上期上升 50.0%" in conclusions["净利润趋势"]
    assert "净利率为 17.3%" in conclusions["净利润趋势"]


def test_picture_brief_trend_single_period_does_not_draw_fake_line(monkeypatch):
    monkeypatch.setattr(app, "get_dashboard_periods", lambda: ["202603"])

    trend = app._picture_brief_trend_frame("2026", "03")

    assert trend.empty
