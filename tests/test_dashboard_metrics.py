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


def _seed_operating_card_companies(conn):
    rows = [
        ("ROOT", "集团根", None, 0, "/ROOT"),
        ("101", "管理中心", "ROOT", 0, "/ROOT/101"),
        ("10101", "素质中心节点", "101", 0, "/ROOT/101/10101"),
        ("1010101", "素质管理中心", "10101", 0, "/ROOT/101/10101/1010101"),
        ("101010101", "素质一校", "1010101", 1, "/ROOT/101/10101/1010101/101010101"),
        ("101010102", "素质二校", "1010101", 1, "/ROOT/101/10101/1010101/101010102"),
        ("101010138", "松山湖校区", "1010101", 1, "/ROOT/101/10101/1010101/101010138"),
        ("10102", "国际教育节点", "101", 0, "/ROOT/101/10102"),
        ("1010201", "深圳卓越", "10102", 1, "/ROOT/101/10102/1010201"),
        ("10107", "幼儿园节点", "101", 0, "/ROOT/101/10107"),
        ("1010702", "新阳光幼儿园", "10107", 1, "/ROOT/101/10107/1010702"),
        ("10108", "多维学校节点", "101", 0, "/ROOT/101/10108"),
        ("1010801", "多维学校", "10108", 1, "/ROOT/101/10108/1010801"),
        ("10118", "青少年宫节点", "101", 0, "/ROOT/101/10118"),
        ("1011801", "莞城青少年宫", "10118", 1, "/ROOT/101/10118/1011801"),
        ("10204", "深圳尔遇文化发展有限公司", "101", 0, "/ROOT/101/10204"),
        ("1020401", "莞城尔遇书馆", "10204", 1, "/ROOT/101/10204/1020401"),
        ("201", "独立公司一", "ROOT", 1, "/ROOT/201"),
        ("202", "独立公司二", "ROOT", 1, "/ROOT/202"),
    ]
    conn.executemany(
        """
        INSERT INTO companies
            (code, name, short_name, parent_code, level, tree_path, is_leaf, is_consolidated, status)
        VALUES (?, ?, ?, ?, 1, ?, ?, 1, 1)
        """,
        [(code, name, name, parent, path, leaf) for code, name, parent, leaf, path in rows],
    )
    conn.executemany(
        """
        INSERT INTO dim_company
            (company_id, company_name, business_group, business_type, region, is_operational)
        VALUES (?, ?, '职能公司模块', '校区', '东莞', 1)
        """,
        [(code, name) for code, name, *_ in rows],
    )


def _insert_operating_card_pl_rows(conn, code, revenue, cost, profit, fee=0.0, main_revenue=None):
    rows = [
        (code, "202603", f"OPERATING_{code}_收入合计", "收入合计", "收入", revenue),
        (code, "202603", f"OPERATING_{code}_成本费用合计", "成本费用合计", "成本", cost),
        (code, "202603", f"OPERATING_{code}_净利润", "净利润", "利润", profit),
    ]
    if main_revenue is not None:
        rows.append((code, "202603", f"DETAIL_{code}_主营业务收入", "主营业务收入", "收入", main_revenue))
    if fee:
        rows.append((code, "202603", f"DETAIL_{code}_管理费服务费", "管理费服务费", "费用", fee))
    conn.executemany(
        """
        INSERT INTO pl_detail
            (company_code, period, item_code, item_name, category, amount)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
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


def test_home_operating_card_group_uses_preferred_pl_rows_for_cost():
    conn = get_connection()
    try:
        _seed_company(conn)
        _insert_duplicate_preferred_pl_rows(conn)
        conn.commit()
    finally:
        conn.close()

    import app

    df = app._query_operating_card_group_by_company("202603", ["001"])

    assert df.loc[0, "模块组/公司"] == "测试公司"
    assert df.loc[0, "经营收入"] == 100.0
    assert df.loc[0, "成本费用合计"] == 80.0
    assert df.loc[0, "经营净利润"] == 20.0
    assert df.loc[0, "净利率"] == pytest.approx(0.2)


def test_home_operating_card_group_fixed_module_mapping_and_scope():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "101", 10.0, 5.0, 5.0)
        _insert_operating_card_pl_rows(conn, "101010101", 100.0, 70.0, 30.0)
        _insert_operating_card_pl_rows(conn, "1010201", 20.0, 10.0, 10.0)
        _insert_operating_card_pl_rows(conn, "1010702", 30.0, 20.0, 10.0)
        _insert_operating_card_pl_rows(conn, "1010801", 40.0, 25.0, 15.0)
        _insert_operating_card_pl_rows(conn, "1011801", 50.0, 30.0, 20.0)
        _insert_operating_card_pl_rows(conn, "10204", 60.0, 30.0, 30.0)
        _insert_operating_card_pl_rows(conn, "1020401", 40.0, 20.0, 20.0)
        conn.commit()
    finally:
        conn.close()

    import app

    df = app._query_operating_card_group_by_company(
        "202603",
        ["101", "101010101", "1010201", "1010702", "1010801", "1011801", "10204", "1020401"],
    )
    labels = [str(value) for value in df["模块组/公司"].tolist()]

    assert labels[-1] == "合计"
    assert "管理中心" in labels[0]
    assert "素质中心" in labels[1]
    assert "国际教育" in labels[2]
    assert "幼儿园" in labels[3]
    assert "多维学校" in labels[4]
    assert "青少年宫" in labels[5]
    assert "尔遇书馆" in labels[6]
    assert df[df["模块组/公司"].astype(str).str.contains("管理中心", regex=False)]["经营收入"].iloc[0] == 10.0
    assert df[df["模块组/公司"].astype(str).str.contains("素质中心", regex=False)]["经营收入"].iloc[0] == 100.0
    assert df[df["模块组/公司"].astype(str).str.contains("尔遇书馆", regex=False)]["经营收入"].iloc[0] == 100.0


def test_home_operating_card_group_leaf_scope_only_shows_own_module_and_total():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "1011801", 50.0, 30.0, 20.0)
        _insert_operating_card_pl_rows(conn, "1010801", 40.0, 25.0, 15.0)
        conn.commit()
    finally:
        conn.close()

    import app

    df = app._query_operating_card_group_by_company("202603", ["1011801"])
    labels = [str(value) for value in df["模块组/公司"].tolist()]

    assert len(df) == 2
    assert "青少年宫" in labels[0]
    assert labels[1] == "合计"
    assert df.iloc[0]["经营收入"] == 50.0


def test_home_operating_card_group_unassigned_companies_stay_separate_and_not_by_business_group():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "201", 11.0, 4.0, 7.0)
        _insert_operating_card_pl_rows(conn, "202", 22.0, 8.0, 14.0)
        conn.commit()
    finally:
        conn.close()

    import app

    df = app._query_operating_card_group_by_company("202603", ["201", "202"])
    labels = [str(value) for value in df["模块组/公司"].tolist()]

    assert labels == ["独立公司一", "独立公司二", "合计"]
    assert "其他" not in labels
    assert "未归集" not in labels
    assert df.iloc[-1]["经营收入"] == 33.0


def test_home_operating_card_group_splits_management_fee_and_keeps_company_detail_raw():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "101", 30.0, 10.0, 20.0)
        _insert_operating_card_pl_rows(conn, "1010101", 100.0, 100.0, 0.0)
        _insert_operating_card_pl_rows(conn, "101010101", 1000.0, 600.0, 400.0, fee=80.0, main_revenue=800.0)
        _insert_operating_card_pl_rows(conn, "101010102", 500.0, 250.0, 250.0, fee=30.0, main_revenue=200.0)
        _insert_operating_card_pl_rows(conn, "101010138", 100.0, 50.0, 50.0, fee=10.0, main_revenue=100.0)
        conn.commit()
    finally:
        conn.close()

    import app

    company_codes = ["101", "1010101", "101010101", "101010102", "101010138"]
    df = app._query_operating_card_group_by_company("202603", company_codes)
    management = df[df["模块组/公司"].astype(str).str.contains("管理中心", regex=False)].iloc[0]
    quality = df[df["模块组/公司"].astype(str).str.contains("素质中心", regex=False)].iloc[0]
    total = df[df["模块组/公司"] == "合计"].iloc[0]

    assert management["经营收入"] == 30.0
    assert management["成本费用合计"] == 10.0
    assert quality["经营收入"] == 1600.0
    assert quality["成本费用合计"] == 900.0
    assert quality["经营净利润"] == 700.0
    assert total["经营收入"] == 1610.0
    assert total["成本费用合计"] == 890.0
    assert total["经营净利润"] == 720.0

    detail = app._query_operating_card_group_by_company("202603", company_codes, "quality")
    center = detail[detail["公司"] == "素质管理中心"].iloc[0]
    songshanhu = detail[detail["公司"] == "松山湖校区"].iloc[0]
    assert center["经营收入"] == 100.0
    assert center["成本费用合计"] == 100.0
    assert songshanhu["经营收入"] == 100.0
    assert songshanhu["成本费用合计"] == 50.0

    reconciliation = app._query_operating_card_fee_reconciliation("202603", company_codes)
    split = reconciliation.set_index("company_code")
    assert split.loc["101010101", "理论非学科服务费"] == 80.0
    assert split.loc["101010102", "理论非学科服务费"] == 20.0
    assert "101010138" in split.index
    assert split.loc["101010138", "理论非学科服务费"] == 0.0
    assert split.loc["101010102", "推定101管理中心收费"] == 10.0
    assert split.loc["101010138", "推定101管理中心收费"] == 10.0


def test_home_operating_card_group_splits_eryu_fee_out_of_101_management():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "10204", 100.0, 40.0, 60.0, main_revenue=30.0)
        _insert_operating_card_pl_rows(conn, "1020401", 200.0, 120.0, 80.0, fee=30.0, main_revenue=200.0)
        conn.commit()
    finally:
        conn.close()

    import app

    app._operating_card_bridge_summary_cached.clear()
    company_codes = ["10204", "1020401"]
    df = app._query_operating_card_group_by_company("202603", company_codes)
    eryu = df[df["模块组/公司"].astype(str).str.contains("尔遇书馆", regex=False)].iloc[0]
    total = df[df["模块组/公司"] == "合计"].iloc[0]

    assert eryu["经营收入"] == 270.0
    assert eryu["成本费用合计"] == 130.0
    assert eryu["经营净利润"] == 140.0
    assert total["经营收入"] == 270.0
    assert total["成本费用合计"] == 130.0
    assert total["经营净利润"] == 140.0

    reconciliation = app._query_operating_card_fee_reconciliation("202603", company_codes)
    split = reconciliation.set_index("company_code")
    assert split.loc["1020401", "理论10204服务费"] == 30.0
    assert split.loc["1020401", "推定101管理中心收费"] == 0.0
    assert split.loc["1020401", "未匹配10204服务费"] == 0.0

    detail = app._query_operating_card_group_by_company("202603", company_codes, "eryu")
    center = detail[detail["公司"] == "深圳尔遇文化发展有限公司"].iloc[0]
    child = detail[detail["公司"] == "莞城尔遇书馆"].iloc[0]
    assert center["经营收入"] == 100.0
    assert child["成本费用合计"] == 120.0


def test_home_operating_card_group_caps_eryu_elimination_to_receiver_internal_income():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "10204", 100.0, 40.0, 60.0, main_revenue=20.0)
        _insert_operating_card_pl_rows(conn, "1020401", 200.0, 120.0, 80.0, fee=30.0, main_revenue=200.0)
        conn.commit()
    finally:
        conn.close()

    import app

    app._operating_card_bridge_summary_cached.clear()
    company_codes = ["10204", "1020401"]
    df = app._query_operating_card_group_by_company("202603", company_codes)
    eryu = df[df["模块组/公司"].astype(str).str.contains("尔遇书馆", regex=False)].iloc[0]
    assert eryu["经营收入"] == 280.0
    assert eryu["成本费用合计"] == 140.0
    assert eryu["经营净利润"] == 140.0

    reconciliation = app._query_operating_card_fee_reconciliation("202603", company_codes)
    split = reconciliation.set_index("company_code")
    assert split.loc["1020401", "理论10204服务费"] == 20.0
    assert split.loc["1020401", "未匹配10204服务费"] == 10.0
    assert split.loc["1020401", "推定101管理中心收费"] == 0.0


def test_home_operating_card_group_does_not_eliminate_eryu_fee_without_receiver_in_scope():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "10204", 100.0, 40.0, 60.0, main_revenue=30.0)
        _insert_operating_card_pl_rows(conn, "1020401", 200.0, 120.0, 80.0, fee=30.0, main_revenue=200.0)
        conn.commit()
    finally:
        conn.close()

    import app

    app._operating_card_bridge_summary_cached.clear()
    company_codes = ["1020401"]
    df = app._query_operating_card_group_by_company("202603", company_codes)
    eryu = df[df["模块组/公司"].astype(str).str.contains("尔遇书馆", regex=False)].iloc[0]
    assert eryu["经营收入"] == 200.0
    assert eryu["成本费用合计"] == 120.0

    bridge = app._operating_card_bridge_summary_cached("202603", tuple(company_codes))
    assert bridge["eryu_fee"] == 0.0
    assert bridge["unmatched_eryu_fee"] == 30.0
    assert bridge["management_fee"] == 0.0
    assert bridge["consolidated_revenue"] == 200.0


def test_home_company_rank_bridge_explains_raw_rank_and_consolidated_operating_revenue():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "101", 30.0, 10.0, 20.0)
        _insert_operating_card_pl_rows(conn, "1010101", 100.0, 100.0, 0.0)
        _insert_operating_card_pl_rows(conn, "101010101", 1000.0, 600.0, 400.0, fee=120.0, main_revenue=800.0)
        _insert_operating_card_pl_rows(conn, "10204", 100.0, 40.0, 60.0, main_revenue=30.0)
        _insert_operating_card_pl_rows(conn, "1020401", 200.0, 120.0, 80.0, fee=30.0, main_revenue=200.0)
        conn.commit()
    finally:
        conn.close()

    import app

    app._operating_card_bridge_summary_cached.clear()
    company_codes = ("101", "1010101", "101010101", "10204", "1020401")
    bridge = app._operating_card_bridge_summary_cached("202603", company_codes)

    assert bridge["raw_revenue"] == 1430.0
    assert bridge["non_subject_fee"] == 100.0
    assert bridge["management_fee"] == 20.0
    assert bridge["eryu_fee"] == 30.0
    assert bridge["total_adjustment"] == 150.0
    assert bridge["consolidated_revenue"] == 1280.0

    html = app._home_company_rank_bridge_html("202603", list(company_codes))
    assert "公司排行采用单体原始口径" in html
    assert "10204" in html
    assert "1430" not in html
    assert "1,430" in html
    assert "1,280" in html


def test_home_operating_panel_summary_matches_group_total_after_elimination():
    conn = get_connection()
    try:
        _seed_operating_card_companies(conn)
        _insert_operating_card_pl_rows(conn, "101", 30.0, 10.0, 20.0)
        _insert_operating_card_pl_rows(conn, "1010101", 100.0, 100.0, 0.0)
        _insert_operating_card_pl_rows(conn, "101010101", 1000.0, 600.0, 400.0, fee=80.0, main_revenue=800.0)
        _insert_operating_card_pl_rows(conn, "101010102", 500.0, 250.0, 250.0, fee=30.0, main_revenue=200.0)
        _insert_operating_card_pl_rows(conn, "101010138", 100.0, 50.0, 50.0, fee=10.0, main_revenue=100.0)
        conn.commit()
    finally:
        conn.close()

    import app

    app._home_operating_summary_for_scope.clear()
    company_codes = ("101", "1010101", "101010101", "101010102", "101010138")
    summary = app._home_operating_summary_for_scope("202603", company_codes)
    detail = app._query_operating_card_group_by_company("202603", list(company_codes))
    total = detail[detail["模块组/公司"] == "合计"].iloc[0]

    assert summary["revenue"] == total["经营收入"] == 1610.0
    assert summary["cost_total"] == total["成本费用合计"] == 890.0
    assert summary["net_profit"] == total["经营净利润"] == 720.0
    assert summary["net_margin"] == pytest.approx(total["净利率"])


def test_home_budget_card_summary_uses_budget_total_row():
    import app

    overview = pd.DataFrame(
        [
            {
                "模块名称": "合计",
                "收入预算": 1000.0,
                "收入实际": 300.0,
                "收入完成率": 0.3,
                "利润预算": -100.0,
                "利润实际": -80.0,
                "利润完成率": None,
                "时间进度": 0.25,
                "收入进度差": 0.05,
                "利润进度差": 0.2,
                "状态": "正常",
            }
        ]
    )

    summary = app._home_budget_card_summary({"progress": overview, "theory_completion": 0.25})

    assert summary["income_completion"] == 0.3
    assert summary["profit_completion"] is None
    assert summary["theory_completion"] == 0.25
    assert summary["profit_gap"] == 0.2
    assert summary["status"] == "正常"


def test_budget_execution_card_uses_clear_benchmark_rows():
    import app

    overview = pd.DataFrame(
        [
            {
                "模块名称": "合计",
                "收入完成率": 0.27,
                "利润完成率": 0.22,
                "时间进度": 0.25,
                "收入进度差": 0.02,
                "利润进度差": -0.03,
                "状态": "滞后",
            }
        ]
    )

    html = app._render_budget_execution_panel({"progress": overview, "theory_completion": 0.25})

    assert "home-budget-compare" in html
    assert "收入完成" in html
    assert "利润完成" in html
    assert "27.0%" in html
    assert "22.0%" in html
    assert "时间进度 25.0%" in html
    assert "超前 2.0 个百分点" in html
    assert "滞后 3.0 个百分点" in html
    assert "综合状态：滞后" in html
    assert "复用全面预算口径" not in html
    assert "点击查看经营单位进度" not in html
    assert "收入偏离" not in html
    assert "利润偏离" not in html
    assert "home-budget-time-marker" in app.PAGE_CSS
    assert "font-size: 1.48rem;" in app.PAGE_CSS
    assert "height: 1.05rem;" in app.PAGE_CSS


def test_home_card_group_modal_contract_and_lazy_loading():
    import app

    render_source = inspect.getsource(app.render_home)
    import_upload_source = inspect.getsource(app._render_import_upload_tab)
    budget_panel_source = inspect.getsource(app._render_budget_execution_panel)
    operating_panel_source = inspect.getsource(app._render_operating_summary_panel)
    expense_panel_source = inspect.getsource(app._render_expense_analysis_panel)
    expense_donut_source = inspect.getsource(app._home_expense_donut_html)
    funds_safety_panel_source = inspect.getsource(app._render_funds_safety_panel)
    funds_risk_panel_source = inspect.getsource(app._render_funds_turnover_risk_panel)
    company_rank_panel_source = inspect.getsource(app._render_company_profit_rank_panel)
    anomaly_panel_source = inspect.getsource(app._render_operating_anomaly_panel)
    layer_source = inspect.getsource(app._render_home_card_group_layer)

    assert "HOME_CARD_GROUP_CONFIG" in render_source
    assert "_render_budget_execution_panel" in render_source
    assert "_render_operating_summary_panel" in render_source
    assert "_render_expense_analysis_panel" in render_source
    assert "_render_funds_safety_panel" in render_source
    assert "_render_company_profit_rank_panel" in render_source
    assert "_render_operating_anomaly_panel" in render_source
    assert "_render_funds_turnover_risk_panel" in render_source
    assert "_home_company_rank_summary_for_scope" in render_source
    assert "_home_operating_anomaly_summary_counts_for_scope" in render_source
    assert "_home_funds_summary_for_scope" in render_source
    assert "_home_funds_rows_for_scope" not in render_source
    assert "_home_company_rank_detail_for_scope(period" not in render_source
    assert "_home_operating_anomaly_detail_for_scope(period" not in render_source
    assert "_render_health_panel(" not in render_source
    assert "经营体检" not in render_source
    assert "校区收入排行" not in render_source
    assert "经营摘要" not in render_source
    assert "_render_budget_panel(budget)" not in render_source
    assert "_render_home_card_group_layer" in render_source
    assert "_load_home_card_group_detail_cached" not in budget_panel_source
    assert "_load_home_card_group_detail_cached" not in operating_panel_source
    assert "_load_home_card_group_detail_cached" not in expense_panel_source
    assert "_load_home_card_group_detail_cached" not in funds_safety_panel_source
    assert "_load_home_card_group_detail_cached" not in company_rank_panel_source
    assert "_load_home_card_group_detail_cached" not in anomaly_panel_source
    assert "_load_home_card_group_detail_cached" not in funds_risk_panel_source
    assert "home-budget-compare" in budget_panel_source
    assert "home-expense-donut-layout" in expense_donut_source
    assert "home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .bi-panel-title" in app.PAGE_CSS
    assert "font-size: 1.32rem;" in app.PAGE_CSS
    assert "home-card-group-grid .home-card-group-link:not(.home-card-group-company-profit-rank) .home-card-mini-value" in app.PAGE_CSS
    assert "_home_funds_rows_for_scope" not in funds_safety_panel_source
    assert "_home_funds_rows_for_scope" not in funds_risk_panel_source
    assert "_load_home_card_group_detail_cached" in layer_source
    assert "home-detail-overlay" in layer_source
    assert "home-detail-modal" in layer_source
    assert "home-detail-drawer" not in layer_source
    assert "home_group" in render_source
    assert "drill_metric not in HOME_DRILL_CONFIG" in render_source
    assert 'class="bi-section-grid home-card-group-grid"' in render_source
    assert 'class="bi-section-grid"' in import_upload_source
    assert "home-card-group-grid" not in import_upload_source
    section_grid_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".bi-section-grid {") : app.PAGE_CSS.index(".home-card-group-grid {")
    ]
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in section_grid_css
    home_grid_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".home-card-group-grid {") : app.PAGE_CSS.index(".home-card-group-grid > .home-card-group-company-profit-rank")
    ]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in home_grid_css
    assert "align-items: start;" in home_grid_css
    assert app.PAGE_CSS.index(".home-card-group-grid > .home-card-group-company-profit-rank") > app.PAGE_CSS.index(".home-card-group-grid {")
    assert "grid-column: 1 / -1;" in app.PAGE_CSS
    assert ".home-rank-two-col" in app.PAGE_CSS
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in app.PAGE_CSS
    assert ".home-rank-table-head" in app.PAGE_CSS
    assert ".home-rank-column-head" in app.PAGE_CSS
    assert ".home-rank-dual-margin" in app.PAGE_CSS
    assert ".home-rank-dual-margin.loss" in app.PAGE_CSS
    assert ".home-card-group-company-profit-rank .bi-panel-title" in app.PAGE_CSS
    assert ".home-card-group-company-profit-rank .home-rank-column-title" in app.PAGE_CSS
    assert "height: 0.62rem;" in app.PAGE_CSS
    assert "white-space: nowrap;" in app.PAGE_CSS
    mobile_css = app.PAGE_CSS[app.PAGE_CSS.index("@media (max-width: 1100px)") :]
    assert ".home-rank-two-col" in mobile_css
    assert "grid-template-columns: 1fr;" in mobile_css
    assert ".home-card-group-company-profit-rank .home-rank-dual-row" in app.PAGE_CSS
    assert render_source.index("_render_budget_execution_panel") < render_source.index("_render_operating_summary_panel")
    assert render_source.index("_render_operating_summary_panel") < render_source.index("_render_expense_analysis_panel")
    assert render_source.index("_render_expense_analysis_panel") < render_source.index("_render_operating_anomaly_panel")
    assert render_source.index("_render_operating_anomaly_panel") < render_source.index("_render_company_profit_rank_panel")
    assert render_source.index("_render_company_profit_rank_panel") < render_source.index("_render_funds_safety_panel")
    assert render_source.index("_render_funds_safety_panel") < render_source.index("_render_funds_turnover_risk_panel")
    assert "资金保障能力" in funds_safety_panel_source
    assert "home-funds-assurance" in funds_safety_panel_source
    assert "近6月月均经营成本" in funds_safety_panel_source
    assert "3个月安全资金线" in funds_safety_panel_source
    assert "安全余量" in funds_safety_panel_source
    assert "home-funds-assurance-grid" in app.PAGE_CSS
    assert "home-funds-assurance-conclusion" in app.PAGE_CSS
    assert list(app.HOME_CARD_GROUP_CONFIG) == [
        "budget_execution",
        "operating_summary",
        "expense_analysis",
        "operating_anomaly",
        "company_profit_rank",
        "funds_safety",
        "funds_turnover_risk",
    ]


def test_home_expense_card_group_shows_bridge_note_without_changing_amounts():
    import app

    analysis = {
        "categories": pd.DataFrame(
            [
                {"费用类别": "人工成本", "本月金额": 800.0, "占成本费用比": 0.4, "占收入比": 0.2},
                {"费用类别": "租金水电物业", "本月金额": 100.0, "占成本费用比": 0.05, "占收入比": 0.025},
            ]
        ),
        "management_fee": {"amount": 90.0},
        "expense_bridge": {
            "label": "其他费用",
            "other_fee": 124.0,
            "check_difference": 0.0,
            "status": "ok",
        },
    }

    html = app._render_expense_analysis_panel(analysis)

    assert "home-expense-donut-layout" in html
    assert "conic-gradient" in html
    assert "六类重点费用合计" in html
    assert "home-expense-bridge-rows" in html
    assert "900" in html
    assert "人工成本" in html
    assert "88.9%" in html
    assert "租金水电物业" in html
    assert "11.1%" in html
    assert "管理费服务费" in html
    assert "其他费用" in html
    assert "成本费用合计 = 六类重点费用 + 管理费服务费 + 其他费用" in html
    assert "口径状态" not in html
    assert "home-expense-legend" in app.PAGE_CSS
    assert "grid-template-columns: minmax(0, 0.64fr) minmax(0, 0.36fr);" in app.PAGE_CSS
    assert "width: clamp(320px, 32vw, 520px);" in app.PAGE_CSS
    assert "width: min(360px, 72vw);" in app.PAGE_CSS
    assert "font-size: 1.38rem;" in app.PAGE_CSS


def test_home_p0_3c_company_rank_card_group_detail_and_dual_bars(monkeypatch):
    import app

    rows = []
    for idx in range(7):
        rows.append(
            {
                "company_code": f"00{idx}",
                "公司": f"测试公司{idx}",
                "业务板块": "测试板块",
                "本月收入": 100.0 - idx,
                "上月收入": 80.0 - idx,
                "去年同期收入": 90.0 - idx,
                "收入环比": 0.1,
                "收入同比": 0.2,
                "本月净利润": -10.0 if idx == 1 else 20.0 - idx,
                "上月净利润": 10.0,
                "去年同期净利润": 15.0,
                "利润环比": -0.1,
                "利润同比": 0.05,
                "本月成本费用": 50.0,
                "上月成本费用": 45.0,
                "成本费用环比": 0.02,
                "本月净利率": -0.1 if idx == 1 else 0.2,
                "上月净利率": 0.18,
                "净利率变化": 0.02,
                "收入排名": idx + 1,
                "利润排名": idx + 1,
                "收入占比": 0.1,
                "利润贡献": 0.1,
            }
        )
    comparison = pd.DataFrame(rows)
    monkeypatch.setattr(app, "_home_company_operating_comparison_frame", lambda period, codes: comparison.copy())
    monkeypatch.setattr(
        app,
        "_home_company_operating_metrics_for_scope",
        lambda period, codes: comparison.rename(
            columns={
                "本月收入": "收入",
                "本月净利润": "净利润",
                "本月成本费用": "成本费用合计",
                "本月净利率": "净利率",
            }
        )[["company_code", "公司", "业务板块", "收入", "成本费用合计", "净利润", "净利率"]].copy(),
    )
    app._home_company_rank_detail_for_scope.clear()

    detail = app._load_home_card_group_detail("company_profit_rank", "202603", ["001", "002"])
    html = app._render_company_profit_rank_panel(detail, None)
    app._home_company_rank_summary_for_scope.clear()
    summary = app._home_company_rank_summary_for_scope("202603", ("001", "002"))
    profit_top, profit_bottom = app._home_company_rank_panel_slices(summary)

    assert len(detail) == 7
    assert len(summary) == 7
    assert list(detail.columns) == [
        "公司",
        "业务板块",
        "经营收入",
        "收入排名",
        "经营净利润",
        "利润排名",
        "净利率",
        "收入占比",
        "利润贡献",
        "收入环比",
        "收入同比",
        "利润环比",
        "利润同比",
    ]
    assert list(profit_top["公司"]) == ["测试公司0", "测试公司2", "测试公司3", "测试公司4", "测试公司5"]
    assert list(profit_bottom["公司"]) == ["测试公司1", "测试公司6", "测试公司5", "测试公司4", "测试公司3"]
    assert len(profit_top) <= 5
    assert len(profit_bottom) <= 5
    assert "home-rank-two-col" in html
    assert "home-rank-table-head" in html
    assert "home-rank-column-head" in html
    assert "盈利前五" in html
    assert "利润倒数前五" in html
    assert "home-rank-dual-row" in html
    assert "home-card-group-company-profit-rank" in html
    assert "home-rank-dual-fill loss" in html
    assert "home-rank-dual-margin profit" in html
    assert "home-rank-dual-margin loss" in html
    assert "净利率 20.0%" not in html
    assert "净利率 -10.0%" not in html
    assert ">20.0%<" in html
    assert ">-10.0%<" in html
    assert "口径状态" in html
    assert "沿用现有口径" in html
    assert html.count("home-rank-dual-row") == 10
    assert html.count("净利率") == 2


def test_home_company_rank_two_column_handles_small_and_empty_sets():
    import app

    small = pd.DataFrame(
        [
            {"公司": "盈利公司", "业务板块": "测试", "经营收入": 120.0, "经营净利润": 9.0, "净利率": 0.08},
            {"公司": "亏损公司", "业务板块": "测试", "经营收入": 80.0, "经营净利润": -3.0, "净利率": -0.04},
            {"公司": "持平公司", "业务板块": "测试", "经营收入": 20.0, "经营净利润": 0.0, "净利率": 0.0},
            {"公司": "缺失公司", "业务板块": "测试", "经营收入": 10.0, "经营净利润": -1.0, "净利率": None},
        ]
    )
    profit_top, profit_bottom = app._home_company_rank_panel_slices(small)
    html = app._render_company_profit_rank_panel(small, None)

    assert list(profit_top["公司"]) == ["盈利公司"]
    assert list(profit_bottom["公司"]) == ["亏损公司", "缺失公司", "持平公司", "盈利公司"]
    assert len(profit_top) <= 5
    assert len(profit_bottom) <= 5
    assert html.count("home-rank-dual-row") == 5
    assert "净利率 暂无" not in html
    assert ">暂无<" in html
    assert html.count("净利率") == 2

    all_loss = pd.DataFrame(
        [
            {"公司": "亏损A", "业务板块": "测试", "经营收入": 80.0, "经营净利润": -3.0, "净利率": -0.04},
            {"公司": "亏损B", "业务板块": "测试", "经营收入": 70.0, "经营净利润": -8.0, "净利率": -0.1},
        ]
    )
    loss_html = app._render_company_profit_rank_panel(all_loss, None)
    assert "暂无盈利公司" in loss_html
    assert loss_html.count("home-rank-dual-row") == 2
    assert loss_html.count("净利率") == 2


def test_home_p0_3c_operating_anomaly_thresholds_missing_history_and_tags(monkeypatch):
    import app

    comparison = pd.DataFrame(
        [
            {
                "公司": "异常公司",
                "业务板块": "测试板块",
                "本月收入": 70.0,
                "上月收入": 100.0,
                "去年同期收入": 100.0,
                "收入环比": -0.3,
                "收入同比": -0.3,
                "本月净利润": 10.0,
                "上月净利润": 30.0,
                "去年同期净利润": 40.0,
                "利润环比": -0.666,
                "利润同比": -0.75,
                "本月成本费用": 130.0,
                "上月成本费用": 100.0,
                "成本费用环比": 0.3,
                "本月净利率": 0.10,
                "上月净利率": 0.18,
                "净利率变化": -0.08,
            },
            {
                "公司": "缺历史公司",
                "业务板块": "测试板块",
                "本月收入": 70.0,
                "上月收入": None,
                "去年同期收入": None,
                "收入环比": None,
                "收入同比": None,
                "本月净利润": 10.0,
                "上月净利润": None,
                "去年同期净利润": None,
                "利润环比": None,
                "利润同比": None,
                "本月成本费用": 80.0,
                "上月成本费用": None,
                "成本费用环比": None,
                "本月净利率": 0.1,
                "上月净利率": None,
                "净利率变化": None,
            },
        ]
    )
    monkeypatch.setattr(app, "_home_company_operating_comparison_frame", lambda period, codes: comparison.copy())
    app._home_operating_anomaly_detail_for_scope.clear()
    app._home_operating_anomaly_summary_counts_for_scope.clear()

    detail = app._load_home_card_group_detail("operating_anomaly", "202603", ["001", "002"])
    counts = app._home_operating_anomaly_counts(detail)
    summary_counts = app._home_operating_anomaly_summary_counts_for_scope("202603", ("001", "002"))
    html = app._render_operating_anomaly_panel(detail, None)

    assert detail["公司"].tolist() == ["异常公司"]
    anomaly_types = detail.iloc[0]["异常类型"]
    for label in app.HOME_OPERATING_ANOMALY_THRESHOLDS:
        assert label in anomaly_types
        assert counts[label] == 1
        assert summary_counts[label] == 1
    assert "缺历史公司" not in detail["公司"].tolist()
    assert "同比/环比经营波动" in html
    assert "按异常事项数统计；缺可比期间不计入异常" in html
    assert "沿用现有阈值" not in html
    assert "home-anomaly-tag" in html


def test_home_operating_anomaly_profit_edge_cases_and_uncomparable_values(monkeypatch):
    import app

    comparison_by_period = {
        "202606": pd.DataFrame(
            [
                {"company_code": "001", "公司": "盈转亏公司", "业务板块": "测试", "收入": 80.0, "成本费用合计": 50.0, "净利润": -5.0, "净利率": -0.0625},
                {"company_code": "002", "公司": "亏损扩大公司", "业务板块": "测试", "收入": 0.0, "成本费用合计": 30.0, "净利润": -20.0, "净利率": None},
                {"company_code": "003", "公司": "亏损收窄公司", "业务板块": "测试", "收入": 20.0, "成本费用合计": 10.0, "净利润": -5.0, "净利率": -0.25},
                {"company_code": "004", "公司": "扭亏公司", "业务板块": "测试", "收入": 20.0, "成本费用合计": 10.0, "净利润": 5.0, "净利率": 0.25},
            ]
        ),
        "202605": pd.DataFrame(
            [
                {"company_code": "001", "公司": "盈转亏公司", "业务板块": "测试", "收入": 100.0, "成本费用合计": 50.0, "净利润": 10.0, "净利率": 0.10},
                {"company_code": "002", "公司": "亏损扩大公司", "业务板块": "测试", "收入": 0.0, "成本费用合计": 10.0, "净利润": -10.0, "净利率": None},
                {"company_code": "003", "公司": "亏损收窄公司", "业务板块": "测试", "收入": 20.0, "成本费用合计": 10.0, "净利润": -10.0, "净利率": -0.50},
                {"company_code": "004", "公司": "扭亏公司", "业务板块": "测试", "收入": 20.0, "成本费用合计": 10.0, "净利润": -10.0, "净利率": -0.50},
            ]
        ),
        "202506": pd.DataFrame(columns=["company_code", "公司", "业务板块", "收入", "成本费用合计", "净利润", "净利率"]),
    }

    monkeypatch.setattr(
        app,
        "_home_company_operating_metrics_for_scope",
        lambda period, codes: comparison_by_period.get(period, pd.DataFrame()).copy(),
    )

    comparison = app._home_company_operating_comparison_frame("202606", ("001", "002", "003", "004"))
    assert comparison.loc[comparison["company_code"] == "001", "利润环比"].iloc[0] == "由盈转亏"
    assert comparison.loc[comparison["company_code"] == "002", "利润环比"].iloc[0] == "亏损扩大"
    assert comparison.loc[comparison["company_code"] == "003", "利润环比"].iloc[0] == "亏损收窄"
    assert comparison.loc[comparison["company_code"] == "004", "利润环比"].iloc[0] == "扭亏"
    assert comparison.loc[comparison["company_code"] == "002", "收入环比"].iloc[0] == app.HOME_UNCOMPARABLE_TEXT
    assert comparison["收入同比"].isna().all()
    assert comparison["利润同比"].isna().all()

    detail = pd.DataFrame(
        [
            anomaly
            for _, row in comparison.iterrows()
            if (anomaly := app._home_anomaly_row_from_comparison(row)) is not None
        ]
    )
    assert detail["公司"].tolist() == ["盈转亏公司", "亏损扩大公司"]
    assert "利润环比下降（由盈转亏）" in detail.iloc[0]["异常类型"]
    assert "利润环比下降（亏损扩大）" in detail.iloc[1]["异常类型"]
    assert set(detail["异常程度/状态"]) == {"高风险"}
    counts = app._home_operating_anomaly_counts(detail)
    assert counts["利润环比下降"] == 2
    assert counts["利润同比下降"] == 0
    assert counts["收入同比下降"] == 0


def test_home_company_rank_filters_missing_metrics_and_sorts_ties_by_company_code(monkeypatch):
    import app

    source = pd.DataFrame(
        [
            {"id": 1, "company_code": "002", "公司": "B公司", "item_code": "OPERATING_收入合计", "item_name": "收入合计", "amount": 100.0},
            {"id": 2, "company_code": "002", "公司": "B公司", "item_code": "OPERATING_成本费用合计", "item_name": "成本费用合计", "amount": 80.0},
            {"id": 3, "company_code": "002", "公司": "B公司", "item_code": "OPERATING_净利润", "item_name": "净利润", "amount": 20.0},
            {"id": 4, "company_code": "001", "公司": "A公司", "item_code": "OPERATING_收入合计", "item_name": "收入合计", "amount": 100.0},
            {"id": 5, "company_code": "001", "公司": "A公司", "item_code": "OPERATING_成本费用合计", "item_name": "成本费用合计", "amount": 80.0},
            {"id": 6, "company_code": "001", "公司": "A公司", "item_code": "OPERATING_净利润", "item_name": "净利润", "amount": 20.0},
            {"id": 7, "company_code": "003", "公司": "缺利润公司", "item_code": "OPERATING_收入合计", "item_name": "收入合计", "amount": 0.0},
            {"id": 8, "company_code": "003", "公司": "缺利润公司", "item_code": "OPERATING_成本费用合计", "item_name": "成本费用合计", "amount": 10.0},
            {"id": 9, "company_code": "10101", "公司": "伪合并节点", "item_code": "OPERATING_收入合计", "item_name": "收入合计", "amount": 999.0},
            {"id": 10, "company_code": "10101", "公司": "伪合并节点", "item_code": "OPERATING_净利润", "item_name": "净利润", "amount": 999.0},
            {"id": 11, "company_code": "10101", "公司": "伪合并节点", "item_code": "OPERATING_成本费用合计", "item_name": "成本费用合计", "amount": 0.0},
        ]
    )
    monkeypatch.setattr(app, "_query_operating_card_source_rows", lambda period, codes: source.copy())
    monkeypatch.setattr(app, "_home_company_business_group_lookup", lambda: {})
    app._home_company_operating_metrics_for_scope.clear()
    app._home_company_rank_summary_for_scope.clear()

    metrics = app._home_company_operating_metrics_for_scope("202606", ("001", "002", "003", "10101"))
    assert "伪合并节点" not in metrics["公司"].tolist()
    assert metrics["公司"].tolist()[:2] == ["A公司", "B公司"]
    missing_profit = metrics.loc[metrics["公司"] == "缺利润公司", "净利润"].iloc[0]
    assert pd.isna(missing_profit)
    assert pd.isna(metrics.loc[metrics["公司"] == "缺利润公司", "净利率"].iloc[0])

    summary = app._home_company_rank_summary_for_scope("202606", ("001", "002", "003", "10101"))
    profit_top, _ = app._home_company_rank_panel_slices(summary)
    assert profit_top["公司"].tolist()[:2] == ["A公司", "B公司"]


def test_home_expense_card_group_detail_uses_module_fee_table(monkeypatch):
    import app

    source = pd.DataFrame(
        [
            {"company_code": "001", "company_name": "模块公司A", "account_code": "OPERATING_001_成本费用合计", "source_item_name": "成本费用合计", "current_amount": 100000.0},
            {"company_code": "001", "company_name": "模块公司A", "account_code": "DETAIL_001_工资", "source_item_name": "工资", "current_amount": 30000.0},
            {"company_code": "001", "company_name": "模块公司A", "account_code": "DETAIL_001_房租", "source_item_name": "房租", "current_amount": 20000.0},
            {"company_code": "001", "company_name": "模块公司A", "account_code": "DETAIL_001_管理费服务费", "source_item_name": "管理费服务费", "current_amount": 10000.0},
            {"company_code": "002", "company_name": "模块公司B", "account_code": "OPERATING_002_成本费用合计", "source_item_name": "成本费用合计", "current_amount": 50000.0},
            {"company_code": "002", "company_name": "模块公司B", "account_code": "DETAIL_002_工资", "source_item_name": "工资", "current_amount": 15000.0},
            {"company_code": "002", "company_name": "模块公司B", "account_code": "DETAIL_002_办公费", "source_item_name": "办公费", "current_amount": 5000.0},
            {"company_code": "002", "company_name": "模块公司B", "account_code": "DETAIL_002_管理费服务费", "source_item_name": "管理费服务费", "current_amount": 5000.0},
            {"company_code": "009", "company_name": "真实未分组公司", "account_code": "OPERATING_009_成本费用合计", "source_item_name": "成本费用合计", "current_amount": 10000.0},
            {"company_code": "009", "company_name": "真实未分组公司", "account_code": "DETAIL_009_工资", "source_item_name": "工资", "current_amount": 12000.0},
            {"company_code": "合计", "company_name": "合计", "account_code": "DETAIL_TOTAL_工资", "source_item_name": "工资", "current_amount": 999999.0},
        ]
    )
    monkeypatch.setattr(app, "get_operating_summary_source_detail", lambda period, codes: source)
    monkeypatch.setattr(
        app,
        "_operating_card_group_scopes",
        lambda codes: [
            {"key": "module", "label": "测试模块", "codes": ["001", "002"], "is_module": True},
            {"key": "company:009", "label": "009", "codes": ["009"], "is_module": False},
        ],
    )

    detail = app._load_home_card_group_detail("expense_analysis", "202603", ["001", "002", "009"])

    assert list(detail.columns) == [
        "模块/公司",
        "人工成本",
        "租金水电物业",
        "折旧摊销",
        "交际接待交通",
        "办公行政",
        "财务费用",
        "管理费服务费",
        "其他费用（或待核对差额）",
        "成本费用合计",
        "占集团成本费用比",
    ]
    assert detail["模块/公司"].tolist() == ["测试模块", "真实未分组公司", "合计"]
    module = detail[detail["模块/公司"] == "测试模块"].iloc[0]
    ungrouped = detail[detail["模块/公司"] == "真实未分组公司"].iloc[0]
    total = detail[detail["模块/公司"] == "合计"].iloc[0]
    assert module["人工成本"] == pytest.approx(4.5)
    assert module["租金水电物业"] == pytest.approx(2.0)
    assert module["办公行政"] == pytest.approx(0.5)
    assert module["管理费服务费"] == pytest.approx(1.5)
    assert module["其他费用（或待核对差额）"] == pytest.approx(6.5)
    assert module["成本费用合计"] == pytest.approx(15.0)
    assert module["占集团成本费用比"] == pytest.approx(0.9375)
    assert ungrouped["其他费用（或待核对差额）"] == pytest.approx(-0.2)
    assert total["成本费用合计"] == pytest.approx(16.0)
    assert total["占集团成本费用比"] == pytest.approx(1.0)
    assert "费用排行" not in app.HOME_CARD_GROUP_CONFIG["expense_analysis"]["subtitle"]
    assert "模块排行" not in app.HOME_CARD_GROUP_CONFIG["expense_analysis"]["subtitle"]

    sorted_detail = app._sort_metric_drilldown_df(detail, "成本费用合计", "desc")
    assert sorted_detail.iloc[-1]["模块/公司"] == "合计"


def test_home_p0_3b_funds_card_group_details_reuse_current_warning_rows(monkeypatch):
    import app

    rows = pd.DataFrame(
        [
            {
                "company_code": "001",
                "公司/校区": "资金紧张公司",
                "货币资金": 100.0,
                "其他应收款": 20.0,
                "其他应付款": 80.0,
                "可使用周转资金": 40.0,
                "近6月平均经营成本": 40.0,
                "资金周转系数": 1.0,
                "资金状态": "资金紧张",
                "has_balance_data": True,
                "business_group": "",
            },
            {
                "company_code": "002",
                "公司/校区": "资金关注公司",
                "货币资金": 120.0,
                "其他应收款": 10.0,
                "其他应付款": 50.0,
                "可使用周转资金": 80.0,
                "近6月平均经营成本": 40.0,
                "资金周转系数": 2.0,
                "资金状态": "资金关注",
                "has_balance_data": True,
                "business_group": "",
            },
            {
                "company_code": "003",
                "公司/校区": "资金安全公司",
                "货币资金": 200.0,
                "其他应收款": 0.0,
                "其他应付款": 20.0,
                "可使用周转资金": 180.0,
                "近6月平均经营成本": 40.0,
                "资金周转系数": 4.5,
                "资金状态": "资金安全",
                "has_balance_data": True,
                "business_group": "",
            },
        ]
    )
    monkeypatch.setattr(app, "_home_funds_rows_for_scope", lambda period, codes: rows.copy())

    safety = app._load_home_card_group_detail("funds_safety", "202603", ["001", "002", "003"])
    risk = app._load_home_card_group_detail("funds_turnover_risk", "202603", ["001", "002", "003"])

    assert list(safety.columns) == ["公司", "货币资金", "其他应收款", "其他应付款", "可使用周转资金", "近6月平均经营成本", "资金周转系数", "资金状态"]
    assert set(safety["公司"]) == {"资金紧张公司", "资金关注公司", "资金安全公司"}
    assert set(risk["公司"]) == {"资金紧张公司", "资金关注公司"}
    assert "最低资金周转系数" not in inspect.getsource(app._render_funds_turnover_risk_panel)
    source = inspect.getsource(app._render_funds_turnover_risk_panel)
    assert "home-card-mini-track" not in source
    assert "home-card-mini-fill" not in source
    summary = app._home_funds_summary_from_rows(rows)
    assert summary["纳入口径近6月平均经营成本合计"] == pytest.approx(120.0)
    assert summary["三个月安全资金线"] == pytest.approx(360.0)
    assert summary["安全余量"] == pytest.approx(-60.0)
    assert summary["集团资金周转系数"] == pytest.approx(2.5)
    safety_html = app._render_funds_safety_panel(summary, None)
    assert "资金保障能力" in safety_html
    assert "近6月月均经营成本" in safety_html
    assert "3个月安全资金线" in safety_html
    assert "安全余量" in safety_html
    assert safety_html.count("集团资金周转系数") == 1
    assert "距离安全线差 0.5 个月 / 需要关注" in safety_html
    assert "资金类仅取科目余额表；其他应收/应付仅取公司往来。" in safety_html
    empty_summary = app._home_funds_summary_from_rows(pd.DataFrame())
    assert empty_summary["纳入口径近6月平均经营成本合计"] is None
    assert "资金数据待接入" in app._render_funds_safety_panel(empty_summary, None)
    html = app._render_funds_turnover_risk_panel(summary, None)
    assert "home-risk-summary-strip" in html
    assert "资金紧张<strong>1 家</strong>" in html
    assert "资金关注<strong>1 家</strong>" in html
    assert "资金安全<strong>1 家</strong>" in html
    assert "风险优先清单" in html
    assert "资金紧张公司" in html
    assert "资金关注公司" in html
    assert "1.00" in html
    assert "2.00" in html
    assert "home-risk-status tight" in html
    assert "home-risk-status watch" in html
    assert "点击查看全部公司" in html
    assert "home-card-mini-track" not in html


def test_home_card_group_table_sort_uses_independent_query_params():
    import app

    html = app._metric_drilldown_table_html(
        pd.DataFrame([{"经营单位": "合计", "收入预算": 100.0, "环比": 0.1}]),
        metric_key="budget_execution",
        key_param="home_group",
        sort_param="home_group_sort",
        order_param="home_group_order",
    )

    assert "home_group=budget_execution" in html
    assert "home_group_sort=%E7%BB%8F%E8%90%A5%E5%8D%95%E4%BD%8D" in html
    assert "drill_metric=" not in html


def test_budget_execution_card_group_detail_respects_company_scope(monkeypatch):
    import app

    plan = pd.DataFrame(
        [
            {"module": "青少年宫", "unit_name": "青少年宫", "income_budget": 400.0, "profit_budget": 40.0, "budget_level": "module"},
            {"module": "多维学校", "unit_name": "多维学校", "income_budget": 500.0, "profit_budget": 50.0, "budget_level": "module"},
            {"module": "合计", "unit_name": "合计", "income_budget": 900.0, "profit_budget": 90.0, "budget_level": "module"},
        ]
    )
    actual = pd.DataFrame(
        [
            {"module": "青少年宫", "unit_name": "少年宫", "company_code": "1011801", "income_actual": 100.0, "profit_actual": 10.0},
            {"module": "多维学校", "unit_name": "多维学校", "company_code": "1010801", "income_actual": 110.0, "profit_actual": 11.0},
        ]
    )
    monkeypatch.setattr(app, "read_budget_plan", lambda: plan)
    monkeypatch.setattr(app, "load_budget_actuals", lambda period: actual)

    detail = app._load_home_card_group_detail("budget_execution", "202603", ["1011801"])

    assert "青少年宫" in set(detail["经营单位"])
    assert "多维学校" not in set(detail["经营单位"])
    assert set(detail["经营单位"]).issubset({"青少年宫", "合计"})
    youth = detail[detail["经营单位"] == "青少年宫"].iloc[0]
    assert youth["收入预算"] == 0.04
    assert youth["收入实际"] == 0.01


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
    assert "extra_grid_class" in kpi_source
    assert 'extra_grid_class="home-top-kpi-grid"' in render_source
    assert "bi-kpi-card selected" in kpi_source
    home_kpi_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".home-top-kpi-grid .bi-kpi-card")
        : app.PAGE_CSS.index(".home-drill-panel-title")
    ]
    assert ".home-top-kpi-grid .bi-kpi-label" in home_kpi_css
    assert "font-size: 1.03rem;" in home_kpi_css
    assert "font-size: 2rem;" in home_kpi_css
    assert "font-size: 0.98rem;" in home_kpi_css
    assert "font-size: 0.9rem;" in home_kpi_css
    global_label_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".bi-kpi-label {") : app.PAGE_CSS.index(".bi-kpi-value {")
    ]
    global_value_css = app.PAGE_CSS[
        app.PAGE_CSS.index(".bi-kpi-value {") : app.PAGE_CSS.index(".bi-kpi-value-link {")
    ]
    assert "font-size: 0.78rem;" in global_label_css
    assert "font-size: 1.03rem;" not in global_label_css
    assert "font-size: 1.42rem;" in global_value_css
    assert "font-size: 2rem;" not in global_value_css
    assert "_app_query_href()" in kpi_source
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
    assert ".home-detail-table-wrap" in app.PAGE_CSS
    assert "overflow: auto;" in app.PAGE_CSS
    assert "max-height: calc(88vh - 10.5rem)" in app.PAGE_CSS
    assert ".home-detail-table th:first-child" in app.PAGE_CSS
    assert ".home-detail-table td:first-child" in app.PAGE_CSS
    assert "position: sticky;" in app.PAGE_CSS
    assert "z-index: 7;" in app.PAGE_CSS
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
