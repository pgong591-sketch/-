import pytest
import inspect
import pandas as pd

from src.db_connection import PROJECT_ROOT, get_connection, get_db_path, init_database
from src.dashboard_metrics import get_home_dashboard


@pytest.fixture(autouse=True)
def isolated_dashboard_database(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard_metrics_test.db"
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(db_path))
    assert get_db_path() == db_path
    assert get_db_path() != PROJECT_ROOT / "data" / "finance_dw.db"
    init_database()


def _seed_company(conn):
    conn.execute(
        """
        INSERT INTO companies
            (code, name, short_name, parent_code, level, tree_path, is_leaf, is_consolidated, status)
        VALUES
            ('001', '测试公司', '测试公司', NULL, 1, '/001', 1, 1, 1)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_company
            (company_id, company_name, business_group, business_type, region, is_operational)
        VALUES ('001', '测试公司', '测试模块', '校区', '东莞', 1)
        """
    )


def _insert_pl_rows(conn, period, revenue, profit, cost):
    conn.executemany(
        """
        INSERT INTO pl_detail
            (company_code, period, item_code, item_name, category, amount)
        VALUES ('001', ?, ?, ?, ?, ?)
        """,
        [
            (period, f"REV_{period}", "收入合计", "收入", revenue),
            (period, f"PROFIT_{period}", "净利润", "利润", profit),
            (period, f"COST_{period}", "成本费用合计", "成本", cost),
        ],
    )


def _insert_balance_rows(conn, period, cash=1000.0, advance=200.0):
    conn.executemany(
        """
        INSERT INTO balance_sheet
            (company_code, period, side, item_name, ending_balance)
        VALUES ('001', ?, ?, ?, ?)
        """,
        [
            (period, "资产", "货币资金", cash),
            (period, "负债和所有者权益", "预收账款", advance),
            (period, "资产", "其他应收款", 100.0),
            (period, "负债和所有者权益", "其他应付款", 50.0),
            (period, "资产", "资产总计", 1500.0),
            (period, "负债和所有者权益", "负债和所有者权益（或股东权益）总计", 1500.0),
        ],
    )


def _insert_duplicate_preferred_pl_rows(conn):
    conn.executemany(
        """
        INSERT INTO pl_detail
            (company_code, period, item_code, item_name, category, amount)
        VALUES ('001', '202603', ?, ?, ?, ?)
        """,
        [
            ("SUMMARY_001_收入合计", "收入合计", "收入", 100.0),
            ("OPERATING_001_收入合计", "收入合计", "收入", 100.0),
            ("DETAIL_001_收入合计", "收入合计", "收入", 999.0),
            ("SUMMARY_002_净利润", "净利润", "利润", 20.0),
            ("OPERATING_002_净利润", "净利润", "利润", 20.0),
            ("SUMMARY_003_成本费用合计", "成本费用合计", "成本", 80.0),
            ("OPERATING_003_成本费用合计", "成本费用合计", "成本", 80.0),
        ],
    )


def test_home_dashboard_uses_pl_detail_for_operating_kpis_and_comparisons():
    conn = get_connection()
    try:
        _seed_company(conn)
        _insert_pl_rows(conn, "202503", revenue=80.0, profit=16.0, cost=64.0)
        _insert_pl_rows(conn, "202602", revenue=100.0, profit=10.0, cost=90.0)
        _insert_pl_rows(conn, "202603", revenue=120.0, profit=30.0, cost=90.0)
        _insert_balance_rows(conn, "202503", cash=600.0, advance=100.0)
        _insert_balance_rows(conn, "202602", cash=800.0, advance=150.0)
        _insert_balance_rows(conn, "202603", cash=1000.0, advance=200.0)
        conn.executemany(
            """
            INSERT INTO income_statement
                (company_code, period, item_name, period1_value, cumulative_value, sort_order)
            VALUES ('001', '202603', ?, ?, ?, 1)
            """,
            [
                ("一、营业收入", 999.0, 999.0),
                ("四、净利润（净亏损以“-”号填列）", 999.0, 999.0),
                ("净利率", 999.0, 999.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    dashboard = get_home_dashboard("202603", explicit_company_codes=["001"])
    kpis = {item["label"]: item for item in dashboard["kpis"]}

    assert dashboard["income"]["revenue"] == 120.0
    assert dashboard["income"]["net_profit"] == 30.0
    assert dashboard["income"]["net_margin"] == 0.25
    assert kpis["本月收入"]["value"] == 120.0
    assert kpis["本月净利润"]["value"] == 30.0
    assert kpis["净利率"]["value"] == 0.25
    assert kpis["本月收入"]["comparisons"]["同比"]["value"] == pytest.approx(0.5)
    assert kpis["本月收入"]["comparisons"]["环比"]["value"] == pytest.approx(0.2)
    assert kpis["净利率"]["comparisons"]["同比"]["value"] == pytest.approx(0.05)
    assert kpis["净利率"]["comparisons"]["环比"]["value"] == pytest.approx(0.15)


def test_home_dashboard_prefers_operating_pl_rows_without_double_counting():
    conn = get_connection()
    try:
        _seed_company(conn)
        _insert_duplicate_preferred_pl_rows(conn)
        _insert_balance_rows(conn, "202603")
        conn.commit()
    finally:
        conn.close()

    dashboard = get_home_dashboard("202603", explicit_company_codes=["001"])

    assert dashboard["income"]["revenue"] == 100.0
    assert dashboard["income"]["net_profit"] == 20.0
    assert dashboard["income"]["cost_run_rate"] == 80.0
    assert dashboard["income"]["net_margin"] == 0.2


def test_home_dashboard_pl_drilldown_uses_same_preferred_rows():
    conn = get_connection()
    try:
        _seed_company(conn)
        _insert_duplicate_preferred_pl_rows(conn)
        conn.commit()
    finally:
        conn.close()

    import app

    df = app._query_pl_metric_by_company("202603", ["001"])

    assert df.loc[0, "收入"] == 100.0
    assert df.loc[0, "净利润"] == 20.0


def test_home_budget_completion_yoy_is_empty_without_comparable_budget_year(monkeypatch):
    import app

    def fake_budget_summary(period):
        if period == "202603":
            return {"year": "2026", "income_completion": 0.3, "profit_completion": 0.2}
        if period == "202602":
            return {"year": "2026", "income_completion": 0.25, "profit_completion": 0.18}
        if period == "202503":
            return {"year": "2025", "income_completion": 0.9, "profit_completion": 0.8}
        return {}

    monkeypatch.setattr(app, "_home_budget_summary_from_budget_dashboard", fake_budget_summary)

    comparisons = app._home_budget_completion_comparisons("202603", "income_completion")

    assert comparisons["同比"]["value"] is None
    assert comparisons["环比"]["value"] == pytest.approx(0.05)


def test_home_dashboard_drill_config_covers_all_eight_kpis():
    import app

    labels = {config["label"] for config in app.HOME_DRILL_CONFIG.values()}
    render_source = inspect.getsource(app.render_home)
    kpi_source = inspect.getsource(app._render_bi_kpi_grid)
    layer_source = inspect.getsource(app._render_metric_drilldown_layer)

    assert labels == {
        "本月收入",
        "本月净利润",
        "净利率",
        "收入年度完成率",
        "利润年度完成率",
        "货币资金",
        "预收账款",
        "资产负债平衡差",
    }
    assert "_render_metric_drilldown_layer" in render_source
    assert "_load_metric_drilldown_cached" in layer_source
    assert "_load_metric_drilldown_cached" not in kpi_source
    assert "show_metric_drilldown_dialog" not in render_source
    assert "_kpi_comparisons_html" in kpi_source
    assert "selected_metric_key" in kpi_source
    assert "bi-kpi-card selected" in kpi_source
    assert 'href = "?"' in kpi_source
    assert {app._metric_drilldown_layer_type(key) for key in app.HOME_DRILL_CONFIG} == {"modal"}
    assert "home-detail-overlay" in layer_source
    assert "z-index: 1000000" in app.PAGE_CSS
    assert "home-detail-drawer" not in layer_source
    assert ".home-detail-drawer" not in app.PAGE_CSS
    assert "home-detail-modal" in app.PAGE_CSS
    assert "width: min(92vw, 1440px)" in app.PAGE_CSS
    assert "height: min(88vh, 900px)" in app.PAGE_CSS
    assert "home-detail-sort" in app.PAGE_CSS
    assert "col-company" in app.PAGE_CSS
    assert "_metric_drilldown_layer_type" in layer_source
    assert '<a class="home-detail-close"' in layer_source
    assert "home_detail_close_" not in layer_source
    assert hasattr(app._home_budget_summary_from_budget_dashboard, "clear")


def test_home_drilldown_table_has_sortable_headers_and_compact_company_column():
    import app

    df = pd.DataFrame(
        [
            {
                "公司": "广东多维教育科技集团有限公司",
                "业务板块": "管理中心",
                "收入": 100.0,
                "环比": 0.1,
                "同比": 0.2,
            }
        ]
    )

    html = app._metric_drilldown_table_html(
        df,
        metric_key="revenue",
        current_sort=None,
        current_order=None,
    )

    assert 'class="home-detail-sort"' in html
    assert "drill_sort=%E5%85%AC%E5%8F%B8" in html
    assert 'class="col-company"' in html
    assert 'title="广东多维教育科技集团有限公司"' in html
    assert html.index("环比") < html.index("同比")


def test_home_drilldown_table_keeps_single_line_balanced_columns():
    import app

    html = app._metric_drilldown_table_html(
        pd.DataFrame(
            [
                {
                    "公司": "广东多维教育科技集团有限公司",
                    "业务板块": "管理中心",
                    "收入": 100.0,
                    "收入占比": 0.6,
                    "环比": 0.1,
                    "同比": 0.2,
                }
            ]
        ),
        metric_key="revenue",
    )

    home_table_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".home-detail-table th,"):
        app.PAGE_CSS.index(".home-detail-table th {")
    ]
    assert "white-space: nowrap" in home_table_css
    assert "text-overflow: ellipsis" in home_table_css
    assert "word-break: break-word" not in home_table_css
    assert "--home-detail-column-count:6" in html
    assert 'class="col-company" style="width:19.35%"' in html
    assert 'class="col-text" style="width:16.13%"' in html
    assert 'title="广东多维教育科技集团有限公司"' in html
    assert 'title="管理中心"' in html


def test_home_drilldown_company_sort_uses_text_order_for_numeric_like_names():
    import app

    df = pd.DataFrame(
        [
            {"公司": "中文名称", "收入": 30.0},
            {"公司": "101", "收入": 10.0},
            {"公司": "2", "收入": 20.0},
        ]
    )

    sorted_df = app._sort_metric_drilldown_df(df, "公司", "asc")

    assert sorted_df["公司"].tolist() == ["101", "2", "中文名称"]


def test_home_revenue_drilldown_adds_yoy_after_mom(monkeypatch):
    import app

    def fake_query(period, company_codes):
        values = {
            "202603": {"收入": 150.0, "净利润": 30.0},
            "202602": {"收入": 100.0, "净利润": 20.0},
            "202503": {"收入": 120.0, "净利润": 24.0},
        }[period]
        return pd.DataFrame(
            [
                {
                    "公司编码": "101",
                    "公司": "管理中心",
                    "业务板块": "管理中心",
                    **values,
                }
            ]
        )

    monkeypatch.setattr(app, "_query_pl_metric_by_company", fake_query)

    df = app._load_metric_drilldown("revenue", "202603", "202602", ["101"])

    assert list(df.columns) == ["公司", "业务板块", "收入", "收入占比", "环比", "同比"]
    assert df.iloc[0]["环比"] == pytest.approx(0.5)
    assert df.iloc[0]["同比"] == pytest.approx(0.25)
