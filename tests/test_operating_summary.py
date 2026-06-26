import pandas as pd

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
