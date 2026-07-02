from pathlib import Path

import pandas as pd
import pytest

import app
from src.db_connection import PROJECT_ROOT, get_connection, get_db_path, init_database
from src.excel_exporter import export_income_statement_pivot


@pytest.fixture(autouse=True)
def isolated_income_statement_database(tmp_path, monkeypatch):
    db_path = tmp_path / "income_statement_test.db"
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(db_path))
    assert get_db_path() == db_path
    assert get_db_path() != PROJECT_ROOT / "data" / "finance_dw.db"


def _seed_income_statement_data():
    init_database()
    conn = get_connection()
    try:
        conn.executemany(
            """
            INSERT INTO companies
                (code, name, short_name, parent_code, level, tree_path, is_leaf, is_consolidated, status)
            VALUES
                (?, ?, ?, NULL, 1, ?, 1, 1, 1)
            """,
            [
                ("002", "第二公司", "第二", "/ROOT/002"),
                ("001", "第一公司", "第一", "/ROOT/001"),
            ],
        )
        rows = []
        for period, period_value, cumulative_value in [
            ("202601", 10.0, 10.0),
            ("202602", 20.0, 30.0),
            ("202603", 30.0, 60.0),
        ]:
            rows.append(("002", period, "原始第二", "一、营业收入", period_value, cumulative_value, 1))
            rows.append(("001", period, "原始第一", "一、营业收入", period_value * 2, cumulative_value * 2, 1))
        conn.executemany(
            """
            INSERT INTO income_statement
                (company_code, period, original_name, item_name, period1_value, cumulative_value, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_income_statement_fixed_item_order_and_extra_items():
    raw = pd.DataFrame(
        [
            {"company_code": "001", "original_name": "公司A", "item_name": "额外项目", "sort_order": 999, "statement_value": 7.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 40.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "毛利率", "sort_order": 4, "statement_value": 0.6},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot["项目"].tolist() == ["一、营业收入", "减：营业成本", "毛利率", "额外项目"]


def test_income_statement_company_columns_sort_by_tree_path_and_code():
    raw = pd.DataFrame(
        [
            {"company_code": "002", "original_name": "原始第二", "short_name": "第二", "company_name": "第二公司", "tree_path": "/ROOT/002", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
            {"company_code": "001", "original_name": "原始第一", "short_name": "第一", "company_name": "第一公司", "tree_path": "/ROOT/001", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.columns.tolist() == ["项目", "原始第一", "原始第二"]


def test_income_statement_company_columns_follow_fixed_excel_order_before_tree_path():
    raw = pd.DataFrame(
        [
            {"company_code": "001", "original_name": "少年宫", "short_name": "", "company_name": "", "tree_path": "/ROOT/001", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "002", "original_name": "莞城小学部", "short_name": "", "company_name": "", "tree_path": "/ROOT/999", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
            {"company_code": "003", "original_name": "固定顺序外", "short_name": "", "company_name": "", "tree_path": "/ROOT/000", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 300.0},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.columns.tolist() == ["项目", "莞城小学部", "少年宫", "固定顺序外"]


def test_income_statement_fixed_company_order_dedupes_repeated_excel_header(monkeypatch):
    monkeypatch.setattr(app, "INCOME_STATEMENT_FIXED_COMPANY_ORDER", ["少年宫", "少年宫", "合并"])

    assert app.get_income_statement_fixed_company_order() == ["少年宫", "合并"]


def test_income_statement_maps_duowei_group_name_to_management_center_order():
    raw = pd.DataFrame(
        [
            {"company_code": "101", "original_name": "广东多维教育科技集团有限公司", "short_name": "", "company_name": "", "tree_path": "/ROOT/999", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "1010101", "original_name": "素质管理中心", "short_name": "", "company_name": "", "tree_path": "/ROOT/001", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
            {"company_code": "1", "original_name": "合并", "short_name": "", "company_name": "", "tree_path": "/ROOT/000", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 300.0},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.columns.tolist() == ["项目", "管理中心", "素质管理中心", "合并"]
    assert "广东多维教育科技集团有限公司" not in pivot.columns


def test_income_statement_same_display_name_keeps_separate_company_columns():
    raw = pd.DataFrame(
        [
            {"company_code": "001", "original_name": "同名", "short_name": "", "company_name": "A", "tree_path": "/001", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "002", "original_name": "同名", "short_name": "", "company_name": "B", "tree_path": "/002", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
        ]
    )

    assert app.get_income_statement_company_order(raw) == ["同名", "同名（002）"]

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.columns.tolist() == ["项目", "同名", "同名（002）"]
    row = pivot.loc[pivot["项目"] == "一、营业收入"].iloc[0]
    assert row["同名"] == 100.0
    assert row["同名（002）"] == 200.0


def test_income_statement_computes_missing_gross_margin_and_net_margin_rows():
    raw = pd.DataFrame(
        [
            {"company_code": "001", "original_name": "公司A", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 40.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "毛利", "sort_order": 3, "statement_value": 60.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 25.0},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot["项目"].tolist() == [
        "一、营业收入",
        "减：营业成本",
        "毛利",
        "毛利率",
        "四、净利润（净亏损以“-”号填列）",
        "净利率",
    ]
    assert pivot.loc[pivot["项目"] == "毛利率", "公司A"].iloc[0] == 0.6
    assert pivot.loc[pivot["项目"] == "净利率", "公司A"].iloc[0] == 0.25


def test_income_statement_keeps_source_margin_rows_when_present():
    raw = pd.DataFrame(
        [
            {"company_code": "001", "original_name": "公司A", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 40.0},
            {"company_code": "001", "original_name": "公司A", "item_name": "毛利率", "sort_order": 4, "statement_value": 0.1234},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.loc[pivot["项目"] == "毛利率", "公司A"].iloc[0] == 0.1234


def test_income_statement_computes_missing_margin_cells_per_company_only():
    raw = pd.DataFrame(
        [
            {"company_code": "A", "original_name": "A公司", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 40.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "毛利率", "sort_order": 4, "statement_value": 0.1234},
            {"company_code": "A", "original_name": "A公司", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 30.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "净利率", "sort_order": 16, "statement_value": 0.2222},
            {"company_code": "B", "original_name": "B公司", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
            {"company_code": "B", "original_name": "B公司", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 80.0},
            {"company_code": "B", "original_name": "B公司", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 50.0},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.loc[pivot["项目"] == "毛利率", "A公司"].iloc[0] == 0.1234
    assert pivot.loc[pivot["项目"] == "毛利率", "B公司"].iloc[0] == 0.6
    assert pivot.loc[pivot["项目"] == "净利率", "A公司"].iloc[0] == 0.2222
    assert pivot.loc[pivot["项目"] == "净利率", "B公司"].iloc[0] == 0.25


def test_income_statement_blank_margin_cells_are_computed_per_company():
    raw = pd.DataFrame(
        [
            {"company_code": "A", "original_name": "A公司", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 100.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 40.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "毛利率", "sort_order": 4, "statement_value": 0.1234},
            {"company_code": "A", "original_name": "A公司", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 30.0},
            {"company_code": "A", "original_name": "A公司", "item_name": "净利率", "sort_order": 16, "statement_value": 0.2222},
            {"company_code": "B", "original_name": "B公司", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 200.0},
            {"company_code": "B", "original_name": "B公司", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 80.0},
            {"company_code": "B", "original_name": "B公司", "item_name": "毛利率", "sort_order": 4, "statement_value": None},
            {"company_code": "B", "original_name": "B公司", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 50.0},
            {"company_code": "B", "original_name": "B公司", "item_name": "净利率", "sort_order": 16, "statement_value": ""},
            {"company_code": "C", "original_name": "C公司", "item_name": "一、营业收入", "sort_order": 1, "statement_value": 300.0},
            {"company_code": "C", "original_name": "C公司", "item_name": "减：营业成本", "sort_order": 2, "statement_value": 90.0},
            {"company_code": "C", "original_name": "C公司", "item_name": "毛利率", "sort_order": 4, "statement_value": "   "},
            {"company_code": "C", "original_name": "C公司", "item_name": "四、净利润（净亏损以“-”号填列）", "sort_order": 15, "statement_value": 60.0},
            {"company_code": "C", "original_name": "C公司", "item_name": "净利率", "sort_order": 16, "statement_value": "   "},
        ]
    )

    pivot = app.build_income_statement_pivot(raw)

    assert pivot.loc[pivot["项目"] == "毛利率", "A公司"].iloc[0] == 0.1234
    assert pivot.loc[pivot["项目"] == "净利率", "A公司"].iloc[0] == 0.2222
    assert pivot.loc[pivot["项目"] == "毛利率", "B公司"].iloc[0] == 0.6
    assert pivot.loc[pivot["项目"] == "净利率", "B公司"].iloc[0] == 0.25
    assert pivot.loc[pivot["项目"] == "毛利率", "C公司"].iloc[0] == 0.7
    assert pivot.loc[pivot["项目"] == "净利率", "C公司"].iloc[0] == 0.2


def test_income_statement_compact_view_keeps_only_core_items():
    pivot = pd.DataFrame(
        [
            {"项目": "一、营业收入", "公司A": 100.0},
            {"项目": "减：营业成本", "公司A": 40.0},
            {"项目": "毛利率", "公司A": 0.6},
            {"项目": "四、净利润（净亏损以“-”号填列）", "公司A": 25.0},
            {"项目": "净利率", "公司A": 0.25},
        ]
    )

    compact = app.filter_income_statement_display_rows(pivot, compact_view=True)

    assert compact["项目"].tolist() == [
        "一、营业收入",
        "四、净利润（净亏损以“-”号填列）",
        "毛利率",
        "净利率",
    ]


def test_income_statement_negative_margin_cells_are_highlighted():
    pivot = pd.DataFrame(
        [
            {"项目": "毛利率", "公司A": -0.1234, "公司B": 0.2},
            {"项目": "净利率", "公司A": 0.1, "公司B": -0.05},
        ]
    )
    display = app.format_income_statement_display(pivot)

    html = app._income_statement_table_html(display, pivot)

    assert "-12.34%" in html
    assert "-5.00%" in html
    assert html.count('class="amount-cell negative-rate-cell"') == 2


def test_income_statement_full_year_uses_latest_cumulative_value_only():
    _seed_income_statement_data()

    raw = app._load_income_statement_rows(["202601", "202602", "202603"], use_cumulative=True)
    pivot = app.build_income_statement_pivot(raw)

    assert pivot.loc[pivot["项目"] == "一、营业收入", "原始第一"].iloc[0] == 120.0
    assert pivot.loc[pivot["项目"] == "一、营业收入", "原始第二"].iloc[0] == 60.0


def test_income_statement_multi_month_uses_period_values_sum():
    _seed_income_statement_data()

    raw = app._load_income_statement_rows(["202601", "202602", "202603"], use_cumulative=False)
    pivot = app.build_income_statement_pivot(raw)

    assert pivot.loc[pivot["项目"] == "一、营业收入", "原始第一"].iloc[0] == 120.0
    assert pivot.loc[pivot["项目"] == "一、营业收入", "原始第二"].iloc[0] == 60.0


def test_income_statement_formats_percent_rows_and_amount_rows():
    pivot = pd.DataFrame(
        [
            {"项目": "毛利", "公司A": 1000.0},
            {"项目": "毛利率", "公司A": 0.1234},
            {"项目": "净利率", "公司A": -0.05},
        ]
    )

    display = app.format_income_statement_display(pivot)

    assert display.loc[display["项目"] == "毛利", "公司A"].iloc[0] == "1,000.00"
    assert display.loc[display["项目"] == "毛利率", "公司A"].iloc[0] == "12.34%"
    assert display.loc[display["项目"] == "净利率", "公司A"].iloc[0] == "-5.00%"


def test_income_statement_html_keeps_item_text_visible():
    display = pd.DataFrame(
        [{"项目": "五、净利润（不含计提折旧与摊销）", "公司A": "1,234.00"}]
    )

    html = app._income_statement_table_html(display)

    assert "五、净利润（不含计提折旧与摊销）" in html
    assert "white-space:normal" in html
    assert "word-break:break-word" in html


def test_income_statement_export_pivot_exists_and_writes_file(tmp_path):
    display = pd.DataFrame(
        [
            {"项目": "一、营业收入", "公司A": "1,000.00"},
            {"项目": "毛利率", "公司A": "12.34%"},
        ]
    )

    path = export_income_statement_pivot(display, "2026", file_path=tmp_path / "income_statement.xlsx")

    assert Path(path).exists()
