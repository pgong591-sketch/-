import pandas as pd

import app


def _source_rows():
    rows = [
        ("001", "A校区", "OPERATING_011_成本费用合计", "成本费用合计", 1000.0),
        ("001", "A校区", "OPERATING_012_收入合计", "收入合计", 2000.0),
        ("001", "A校区", "DETAIL_工资", "工资", 400.0),
        ("001", "A校区", "DETAIL_社保费", "社保费", 100.0),
        ("001", "A校区", "DETAIL_房租", "房租", 80.0),
        ("001", "A校区", "DETAIL_水电费", "水电费", 20.0),
        ("001", "A校区", "DETAIL_折旧费", "折旧费", 30.0),
        ("001", "A校区", "DETAIL_待摊费", "待摊费", 10.0),
        ("001", "A校区", "DETAIL_折旧与待摊费用合计", "折旧与待摊费用合计", 40.0),
        ("001", "A校区", "DETAIL_招待费", "招待费", 15.0),
        ("001", "A校区", "DETAIL_市内交通费", "市内交通费", 5.0),
        ("001", "A校区", "DETAIL_办公费", "办公费", 12.0),
        ("001", "A校区", "DETAIL_维修费", "维修费", 8.0),
        ("001", "A校区", "DETAIL_手续费", "手续费", 6.0),
        ("001", "A校区", "DETAIL_管理费服务费", "管理费服务费", 90.0),
        ("002", "B校区", "DETAIL_工资", "工资", 300.0),
    ]
    return pd.DataFrame(
        rows,
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount"],
    )


def _amount_by_category(categories: pd.DataFrame, category: str) -> float:
    return float(categories.loc[categories["费用类别"] == category, "本月金额"].iloc[0])


def test_focus_expense_analysis_groups_six_external_categories():
    analysis = app.build_focus_expense_analysis(_source_rows())
    categories = analysis["categories"]

    assert categories["费用类别"].tolist() == [
        "人工成本",
        "租金水电物业",
        "折旧摊销",
        "交际接待交通",
        "办公行政",
        "财务费用",
    ]
    assert _amount_by_category(categories, "人工成本") == 800.0
    assert _amount_by_category(categories, "租金水电物业") == 100.0
    assert _amount_by_category(categories, "交际接待交通") == 20.0
    assert _amount_by_category(categories, "办公行政") == 20.0
    assert _amount_by_category(categories, "财务费用") == 6.0


def test_focus_expense_analysis_keeps_management_fee_separate():
    analysis = app.build_focus_expense_analysis(_source_rows())
    categories = analysis["categories"]

    assert "管理费服务费" not in categories["费用类别"].tolist()
    assert analysis["management_fee"]["amount"] == 90.0
    assert analysis["management_fee"]["cost_ratio"] == 0.09
    assert "单独提示" in analysis["conclusion"]


def test_focus_expense_analysis_depreciation_does_not_double_count_total_row():
    analysis = app.build_focus_expense_analysis(_source_rows())

    assert _amount_by_category(analysis["categories"], "折旧摊销") == 40.0


def test_focus_expense_ranking_uses_main_company():
    analysis = app.build_focus_expense_analysis(_source_rows())
    ranking = analysis["ranking"]
    labor = ranking.loc[ranking["费用类别"] == "人工成本"].iloc[0]

    assert labor["主要经营单位"] == "A校区"
    assert labor["本月金额"] == 500.0


def test_focus_expense_navigation_entry_reuses_existing_expense_page():
    assert "费用科目分析" in app.NAV_MODULE_SECTIONS["经营中心"]["经营看板"]
    assert app.NAV_LABELS["费用科目分析"] == "费用分析"


def test_focus_expense_cards_render_as_html_without_source_leak(monkeypatch):
    rendered = []
    monkeypatch.setattr(app, "_render_html", lambda markup: rendered.append(markup))

    app._render_focus_expense_cards(app.build_focus_expense_analysis(_source_rows())["categories"])

    assert len(rendered) == 1
    assert rendered[0].count('class="focus-expense-card"') == 6
    assert "&lt;div" not in rendered[0]
    assert "&lt;/div&gt;" not in rendered[0]
    assert "人工成本" in rendered[0]
    assert "财务费用" in rendered[0]
