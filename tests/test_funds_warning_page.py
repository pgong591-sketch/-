import inspect
import math

import pandas as pd

import app


def _companies():
    return pd.DataFrame(
        [
            {"code": "A", "name": "A公司", "short_name": "A校区", "tree_path": "/A", "business_group": "非学科素质中心模块"},
            {"code": "B", "name": "B公司", "short_name": "B校区", "tree_path": "/B", "business_group": "非学科素质中心模块"},
            {"code": "C", "name": "C公司", "short_name": "C校区", "tree_path": "/C", "business_group": "非学科素质中心模块"},
            {"code": "D", "name": "D公司", "short_name": "D校区", "tree_path": "/D", "business_group": "非学科素质中心模块"},
        ]
    )


def _company_tree_for_scope_tests():
    return pd.DataFrame(
        [
            {"code": "P", "name": "父公司", "short_name": "父公司", "tree_path": "/P", "business_group": ""},
            {"code": "C1", "name": "子公司1", "short_name": "子公司1", "tree_path": "/P/C1", "business_group": ""},
            {"code": "C2", "name": "子公司2", "short_name": "子公司2", "tree_path": "/P/C2", "business_group": ""},
            {"code": "1010101", "name": "东莞非学科管理中心", "short_name": "东莞非学科管理中心", "tree_path": "/101/10101/1010101", "business_group": "职能公司模块"},
            {"code": "10204", "name": "深圳尔遇文化发展有限公司", "short_name": "尔遇书馆管理中心", "tree_path": "/102/10204", "business_group": "尔遇书馆模块"},
            {"code": "1020401", "name": "莞城鸿福尔遇书馆", "short_name": "莞城鸿福尔遇书馆", "tree_path": "/102/10204/1020401", "business_group": "尔遇书馆模块"},
        ]
    )


def test_funds_warning_formulas_and_statuses():
    balances = pd.DataFrame(
        [
            {"company_code": "A", "cash": 100.0, "other_receivable": 50.0, "other_payable": 30.0},
            {"company_code": "B", "cash": 200.0, "other_receivable": 40.0, "other_payable": 40.0},
            {"company_code": "C", "cash": 600.0, "other_receivable": 0.0, "other_payable": 0.0},
        ]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "A", "avg_operating_cost": 100.0, "cost_period_count": 6},
            {"company_code": "B", "avg_operating_cost": 100.0, "cost_period_count": 6},
            {"company_code": "C", "avg_operating_cost": 100.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_companies(), balances, costs).set_index("company_code")

    assert rows.loc["A", "实收资本未达账"] == 0.0
    assert rows.loc["A", "可使用周转资金"] == 120.0
    assert rows.loc["A", "资金周转系数"] == 1.2
    assert rows.loc["A", "资金状态"] == "资金紧张"
    assert rows.loc["B", "资金周转系数"] == 2.0
    assert rows.loc["B", "资金状态"] == "资金关注"
    assert rows.loc["C", "资金周转系数"] == 6.0
    assert rows.loc["C", "资金状态"] == "资金安全"


def test_funds_warning_defaults_only_show_warning_companies():
    rows = pd.DataFrame(
        [
            {"company_code": "A", "资金周转系数": 1.99, "资金状态": "资金紧张"},
            {"company_code": "B", "资金周转系数": 2.5, "资金状态": "资金关注"},
            {"company_code": "C", "资金周转系数": 3.0, "资金状态": "资金安全"},
            {"company_code": "D", "资金周转系数": math.nan, "资金状态": "待接入"},
        ]
    )

    filtered = app._funds_warning_filter_rows(rows, "预警公司")

    assert filtered["company_code"].tolist() == ["A", "B"]
    assert app._funds_warning_filter_rows(rows, "资金安全")["company_code"].tolist() == ["C"]
    assert app._funds_warning_filter_rows(rows, "数据待接入")["company_code"].tolist() == ["D"]
    assert app._funds_warning_filter_rows(rows, "全部状态")["company_code"].tolist() == ["A", "B", "C", "D"]


def test_funds_warning_view_scope_filters_do_not_change_row_calculation():
    rows = pd.DataFrame(
        [
            {"company_code": "A", "公司/校区": "南城校区", "business_group": "非学科素质中心模块", "资金周转系数": 1.0},
            {"company_code": "B", "公司/校区": "东莞非学科管理中心", "business_group": "职能公司模块", "资金周转系数": 4.0},
            {"company_code": "C", "公司/校区": "莞城鸿福尔遇书馆", "business_group": "尔遇书馆模块", "资金周转系数": 4.0},
            {"company_code": "D", "公司/校区": "安全公司", "business_group": "", "资金周转系数": 5.0},
        ]
    )

    assert app._funds_warning_filter_scope_rows(rows, "只看校区")["company_code"].tolist() == ["A"]
    assert app._funds_warning_filter_scope_rows(rows, "只看管理中心")["company_code"].tolist() == ["B"]
    assert app._funds_warning_filter_scope_rows(rows, "只看书馆")["company_code"].tolist() == ["C"]
    assert app._funds_warning_filter_scope_rows(rows, "只看资金预警公司")["company_code"].tolist() == ["A"]


def test_funds_warning_sort_options():
    rows = pd.DataFrame(
        [
            {"company_code": "B", "公司/校区": "B公司", "资金状态": "资金关注", "资金周转系数": 2.5, "可使用周转资金": 20.0},
            {"company_code": "A", "公司/校区": "A公司", "资金状态": "资金紧张", "资金周转系数": 1.5, "可使用周转资金": 10.0},
            {"company_code": "C", "公司/校区": "C公司", "资金状态": "资金安全", "资金周转系数": 4.0, "可使用周转资金": -5.0},
        ]
    )

    assert app._funds_warning_sort_rows(rows, "按风险从高到低")["company_code"].tolist() == ["A", "B", "C"]
    assert app._funds_warning_sort_rows(rows, "按可使用周转资金从低到高")["company_code"].tolist() == ["C", "A", "B"]
    assert app._funds_warning_sort_rows(rows, "按公司名称")["company_code"].tolist() == ["A", "B", "C"]


def test_funds_warning_filter_labels_and_defaults_are_business_terms():
    source = inspect.getsource(app.render_funds_warning)

    assert app.FUNDS_WARNING_VIEW_SCOPE_OPTIONS[0] == "全部单体公司"
    assert app.FUNDS_WARNING_STATUS_OPTIONS[0] == "预警公司"
    assert app.FUNDS_WARNING_SORT_OPTIONS[0] == "按风险从高到低"
    assert "查看范围" in source
    assert "资金状态" in source
    assert "排序方式" in source
    assert "公司范围" not in source
    assert "预警状态" not in source
    assert "默认展示资金周转系数低于 3.0 的单体公司；资金类数据仅取科目余额表。" in source


def test_funds_warning_no_cost_data_is_pending_not_error():
    balances = pd.DataFrame(
        [{"company_code": "D", "cash": 100.0, "other_receivable": 0.0, "other_payable": 0.0}]
    )
    costs = pd.DataFrame(columns=["company_code", "avg_operating_cost", "cost_period_count"])

    rows = app._funds_warning_build_rows(_companies(), balances, costs).set_index("company_code")

    assert pd.isna(rows.loc["D", "资金周转系数"])
    assert rows.loc["D", "资金状态"] == "成本数据待接入"


def test_funds_warning_kpis_use_group_turnover_ratio_not_minimum_ratio():
    rows = pd.DataFrame(
        [
            {
                "company_code": "A",
                "business_group": "非学科素质中心模块",
                "has_balance_data": True,
                "可使用周转资金": 100.0,
                "近6月平均经营成本": 50.0,
                "资金周转系数": 2.0,
                "资金状态": "资金关注",
            },
            {
                "company_code": "B",
                "business_group": "非学科素质中心模块",
                "has_balance_data": True,
                "可使用周转资金": 800.0,
                "近6月平均经营成本": 100.0,
                "资金周转系数": 8.0,
                "资金状态": "资金安全",
            },
        ]
    )

    kpis = app._funds_warning_kpis(rows)

    assert "集团资金周转系数" in kpis
    assert "最低资金周转系数" not in kpis
    assert kpis["集团资金周转系数"] == "6.00"


def test_funds_warning_group_turnover_ratio_excludes_investment_scope():
    rows = pd.DataFrame(
        [
            {
                "company_code": "A",
                "business_group": "非学科素质中心模块",
                "has_balance_data": True,
                "可使用周转资金": 100.0,
                "近6月平均经营成本": 50.0,
                "资金周转系数": 2.0,
                "资金状态": "资金关注",
            },
            {
                "company_code": "1010201",
                "business_group": "非学科素质中心模块",
                "has_balance_data": True,
                "可使用周转资金": 9000.0,
                "近6月平均经营成本": 10.0,
                "资金周转系数": 900.0,
                "资金状态": "资金安全",
            },
            {
                "company_code": "101020101",
                "business_group": "非学科素质中心模块",
                "has_balance_data": True,
                "可使用周转资金": 8000.0,
                "近6月平均经营成本": 10.0,
                "资金周转系数": 800.0,
                "资金状态": "资金安全",
            },
            {
                "company_code": "X",
                "business_group": "对外投资模块",
                "has_balance_data": True,
                "可使用周转资金": 7000.0,
                "近6月平均经营成本": 10.0,
                "资金周转系数": 700.0,
                "资金状态": "资金安全",
            },
        ]
    )

    assert app._funds_warning_group_turnover_ratio(rows) == 2.0
    assert set(app._funds_warning_group_ratio_rows(rows)["company_code"]) == {"A"}


def test_funds_warning_no_account_balance_data_is_pending_not_safe():
    balances = pd.DataFrame(columns=["company_code", "cash", "other_receivable", "other_payable", "has_balance_data"])
    costs = pd.DataFrame(
        [
            {"company_code": "A", "avg_operating_cost": 100.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_companies().head(1), balances, costs).set_index("company_code")

    assert pd.isna(rows.loc["A", "货币资金"])
    assert pd.isna(rows.loc["A", "资金周转系数"])
    assert rows.loc["A", "资金状态"] == "资金数据待接入"
    assert app._funds_warning_filter_rows(rows.reset_index(), "预警公司").empty


def test_funds_warning_zero_account_balance_is_valid_data():
    balances = pd.DataFrame(
        [{"company_code": "A", "cash": 0.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True}]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "A", "avg_operating_cost": 100.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_companies().head(1), balances, costs).set_index("company_code")

    assert rows.loc["A", "货币资金"] == 0.0
    assert rows.loc["A", "资金周转系数"] == 0.0
    assert rows.loc["A", "资金状态"] == "资金紧张"


def test_funds_warning_recent_cost_average_and_dedup(monkeypatch):
    def fake_recent_periods(period, limit=6):
        return ["202601", "202602", "202603"]

    def fake_execute_sql(sql, params=None):
        return pd.DataFrame(
            [
                {"id": 1, "company_code": "A", "period": "202601", "item_code": "OPERATING_COST", "amount": 90.0},
                {"id": 2, "company_code": "A", "period": "202602", "item_code": "OPERATING_COST", "amount": 120.0},
                {"id": 3, "company_code": "A", "period": "202603", "item_code": "SUMMARY_COST", "amount": 999.0},
                {"id": 4, "company_code": "A", "period": "202603", "item_code": "OPERATING_COST", "amount": 150.0},
            ]
        )

    monkeypatch.setattr(app, "_funds_warning_recent_periods", fake_recent_periods)
    monkeypatch.setattr(app, "execute_sql", fake_execute_sql)

    costs = app._funds_warning_cost_metrics("202603").set_index("company_code")

    assert costs.loc["A", "cost_period_count"] == 3
    assert costs.loc["A", "avg_operating_cost"] == 120.0


def test_funds_warning_balance_metrics_prefers_parent_accounts(monkeypatch):
    def fake_execute_sql(sql, params=None):
        assert params == {"period": "202603"}
        return pd.DataFrame(
            [
                {"company_code": "A", "account_code": "1002", "account_name": "银行存款", "ending_balance": 50.0},
                {"company_code": "A", "account_code": "100201", "account_name": "银行存款\\工行", "ending_balance": 7.0},
                {"company_code": "A", "account_code": "1012", "account_name": "其他货币资金", "ending_balance": 20.0},
                {"company_code": "A", "account_code": "1221", "account_name": "其他应收款", "ending_balance": 201.0},
                {"company_code": "A", "account_code": "122101", "account_name": "其他应收款\\押金", "ending_balance": 100.0},
                {"company_code": "A", "account_code": "122105", "account_name": "其他应收款\\公司往来", "ending_balance": 12.0},
                {"company_code": "A", "account_code": "2241", "account_name": "其他应付款", "ending_balance": 800.0},
                {"company_code": "A", "account_code": "224101", "account_name": "其他应付款\\公司往来", "ending_balance": 10.0},
            ]
        )

    monkeypatch.setattr(app, "execute_sql", fake_execute_sql)

    rows = app._funds_warning_balance_metrics("202603").set_index("company_code")

    assert rows.loc["A", "cash"] == 70.0
    assert rows.loc["A", "other_receivable"] == 12.0
    assert rows.loc["A", "other_payable"] == 10.0


def test_funds_warning_balance_metrics_falls_back_to_children_without_parent(monkeypatch):
    def fake_execute_sql(sql, params=None):
        return pd.DataFrame(
            [
                {"company_code": "B", "account_code": "100201", "account_name": "银行存款\\工行", "ending_balance": 200.0},
                {"company_code": "B", "account_code": "100202", "account_name": "银行存款\\建行", "ending_balance": 10.0},
                {"company_code": "B", "account_code": "122105", "account_name": "其他应收款\\公司往来", "ending_balance": 100.0},
                {"company_code": "B", "account_code": "122105", "account_name": "其他应收款/公司往来", "ending_balance": 20.0},
                {"company_code": "B", "account_code": "224101", "account_name": "其他应付款\\公司往来", "ending_balance": 30.0},
            ]
        )

    monkeypatch.setattr(app, "execute_sql", fake_execute_sql)

    rows = app._funds_warning_balance_metrics("202603").set_index("company_code")

    assert rows.loc["B", "cash"] == 210.0
    assert rows.loc["B", "other_receivable"] == 120.0
    assert rows.loc["B", "other_payable"] == 30.0


def test_funds_warning_receivable_payable_only_use_company_current(monkeypatch):
    def fake_execute_sql(sql, params=None):
        return pd.DataFrame(
            [
                {"company_code": "A", "account_code": "1221", "account_name": "其他应收款", "ending_balance": 1000.0},
                {"company_code": "A", "account_code": "122101", "account_name": "其他应收款\\代扣社保费", "ending_balance": 200.0},
                {"company_code": "A", "account_code": "122102", "account_name": "其他应收款\\代扣公积金", "ending_balance": 300.0},
                {"company_code": "A", "account_code": "122105", "account_name": "其他应收款\\公司往来", "ending_balance": 40.0},
                {"company_code": "A", "account_code": "122106", "account_name": "其他应收款\\个人往来", "ending_balance": 500.0},
                {"company_code": "A", "account_code": "122107", "account_name": "其他应收款\\其他往来", "ending_balance": 600.0},
                {"company_code": "A", "account_code": "2241", "account_name": "其他应付款", "ending_balance": 2000.0},
                {"company_code": "A", "account_code": "224101", "account_name": "其他应付款\\公司往来", "ending_balance": 70.0},
                {"company_code": "A", "account_code": "224103", "account_name": "其他应付款\\预提费用", "ending_balance": 800.0},
            ]
        )

    monkeypatch.setattr(app, "execute_sql", fake_execute_sql)

    rows = app._funds_warning_balance_metrics("202603").set_index("company_code")

    assert rows.loc["A", "other_receivable"] == 40.0
    assert rows.loc["A", "other_payable"] == 70.0


def test_funds_warning_available_funds_recalculate_with_company_current_receivable_payable():
    balances = pd.DataFrame(
        [{"company_code": "A", "cash": 100.0, "other_receivable": 40.0, "other_payable": 70.0, "has_balance_data": True}]
    )
    costs = pd.DataFrame(
        [{"company_code": "A", "avg_operating_cost": 35.0, "cost_period_count": 6}]
    )

    rows = app._funds_warning_build_rows(_companies().head(1), balances, costs).set_index("company_code")

    assert rows.loc["A", "可使用周转资金"] == 70.0
    assert rows.loc["A", "资金周转系数"] == 2.0
    assert rows.loc["A", "资金状态"] == "资金关注"


def test_funds_warning_balance_metrics_does_not_read_balance_sheet():
    source = inspect.getsource(app._funds_warning_balance_metrics)
    source += inspect.getsource(app._funds_warning_preferred_balance_metrics)
    source += inspect.getsource(app._funds_warning_build_rows)

    assert "balance_sheet" not in source


def test_funds_warning_parent_row_does_not_expand_children():
    balances = pd.DataFrame(
        [
            {"company_code": "P", "cash": 100.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True},
            {"company_code": "C1", "cash": 900.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True},
        ]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "P", "avg_operating_cost": 50.0, "cost_period_count": 6},
            {"company_code": "C1", "avg_operating_cost": 100.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_company_tree_for_scope_tests(), balances, costs).set_index("company_code")

    assert rows.loc["P", "货币资金"] == 100.0
    assert rows.loc["P", "可使用周转资金"] == 100.0
    assert rows.loc["P", "资金周转系数"] == 2.0
    assert rows.loc["C1", "货币资金"] == 900.0


def test_funds_warning_parent_without_self_data_is_not_created_from_children():
    balances = pd.DataFrame(
        [
            {"company_code": "C1", "cash": 900.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True},
        ]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "C1", "avg_operating_cost": 100.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_company_tree_for_scope_tests(), balances, costs)

    assert "P" not in set(rows["company_code"])
    assert rows.set_index("company_code").loc["C1", "货币资金"] == 900.0


def test_funds_warning_non_leaf_management_center_uses_own_data():
    balances = pd.DataFrame(
        [
            {"company_code": "1010101", "cash": 300.0, "other_receivable": 20.0, "other_payable": 50.0, "has_balance_data": True},
        ]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "1010101", "avg_operating_cost": 90.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_company_tree_for_scope_tests(), balances, costs).set_index("company_code")

    assert rows.loc["1010101", "公司/校区"] == "东莞非学科管理中心"
    assert rows.loc["1010101", "可使用周转资金"] == 270.0
    assert rows.loc["1010101", "资金周转系数"] == 3.0


def test_funds_warning_yuer_management_center_does_not_include_bookstore_children():
    balances = pd.DataFrame(
        [
            {"company_code": "10204", "cash": 100.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True},
            {"company_code": "1020401", "cash": 500.0, "other_receivable": 0.0, "other_payable": 0.0, "has_balance_data": True},
        ]
    )
    costs = pd.DataFrame(
        [
            {"company_code": "10204", "avg_operating_cost": 50.0, "cost_period_count": 6},
            {"company_code": "1020401", "avg_operating_cost": 50.0, "cost_period_count": 6},
        ]
    )

    rows = app._funds_warning_build_rows(_company_tree_for_scope_tests(), balances, costs).set_index("company_code")

    assert rows.loc["10204", "公司/校区"] == "尔遇书馆管理中心"
    assert rows.loc["10204", "货币资金"] == 100.0
    assert rows.loc["10204", "资金周转系数"] == 2.0
    assert rows.loc["1020401", "货币资金"] == 500.0


def test_funds_warning_table_html_has_finance_table_contract():
    rows = app._funds_warning_build_rows(
        _companies().head(1),
        pd.DataFrame([{"company_code": "A", "cash": -100.0, "other_receivable": 0.0, "other_payable": 0.0}]),
        pd.DataFrame([{"company_code": "A", "avg_operating_cost": 100.0, "cost_period_count": 1}]),
    )

    html = app._funds_warning_table_html(rows)

    assert "公司资金周转预警清单" in html
    assert "单位：万元" in html
    assert "funds-warning-num" in html
    assert "funds-warning-negative" in html
    assert "&lt;" not in html


def test_funds_warning_styles_align_query_button_without_global_css():
    css = app._funds_warning_styles()

    assert 'st-key-funds_warning_query' in css
    assert "padding-top: 1.72rem" in css
    assert "min-height: 42px" in css
    assert "_filter_apply" not in css
