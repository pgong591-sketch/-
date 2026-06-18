from src.db_connection import get_connection, init_database
from src.multidim_reports import get_multidim_income_statement, get_operating_summary


def _seed_company(conn):
    conn.executemany(
        """
        INSERT INTO companies
            (code, name, short_name, parent_code, level, tree_path, is_leaf, is_consolidated, status)
        VALUES
            (?, ?, ?, NULL, 0, ?, 1, 1, 1)
        """,
        [
            ("001", "测试校区", "测试校区", "/001"),
            ("002", "第二校区", "第二校区", "/002"),
        ],
    )


def _seed_income(conn):
    rows = [
        ("001", "202603", "一、营业收入", 1000.0, 1),
        ("001", "202603", "减：营业成本", 400.0, 2),
        ("001", "202603", "销售费用", 50.0, 3),
        ("001", "202603", "管理费用", 100.0, 4),
        ("001", "202603", "财务费用", 20.0, 5),
        ("001", "202603", "四、净利润（净亏损以“-”号填列）", 300.0, 6),
        ("002", "202603", "一、营业收入", 2000.0, 1),
        ("002", "202603", "减：营业成本", 900.0, 2),
        ("002", "202603", "销售费用", 80.0, 3),
        ("002", "202603", "管理费用", 140.0, 4),
        ("002", "202603", "财务费用", 30.0, 5),
        ("002", "202603", "四、净利润（净亏损以“-”号填列）", 500.0, 6),
    ]
    conn.executemany(
        """
        INSERT INTO income_statement
            (company_code, period, item_name, period1_value, sort_order)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_multidim_income_statement_pivots_companies():
    init_database()
    conn = get_connection()
    try:
        _seed_company(conn)
        _seed_income(conn)
        conn.commit()
    finally:
        conn.close()

    df = get_multidim_income_statement("202603")

    assert "项目" in df.columns
    assert "测试校区" in df.columns
    assert "第二校区" in df.columns
    assert "合计" in df.columns
    assert df.loc[df["项目"] == "一、营业收入", "合计"].iloc[0] == 3000.0


def test_operating_summary_recalculates_margin_rows():
    init_database()
    conn = get_connection()
    try:
        _seed_company(conn)
        _seed_income(conn)
        conn.commit()
    finally:
        conn.close()

    df = get_operating_summary("202603")

    gross_profit = df.loc[df["项目"] == "毛利", "金额"].iloc[0]
    net_margin = df.loc[df["项目"] == "净利润", "占收入比"].iloc[0]
    assert gross_profit == 1700.0
    assert net_margin == 800.0 / 3000.0


def test_operating_summary_can_filter_explicit_company_codes():
    init_database()
    conn = get_connection()
    try:
        _seed_company(conn)
        _seed_income(conn)
        conn.commit()
    finally:
        conn.close()

    df = get_operating_summary("202603", company_codes=["002"])
    detail_df = get_multidim_income_statement("202603", company_codes=["002"])

    revenue = df.loc[df["项目"] == "营业收入", "金额"].iloc[0]
    gross_profit = df.loc[df["项目"] == "毛利", "金额"].iloc[0]
    assert revenue == 2000.0
    assert gross_profit == 1100.0
    assert "第二校区" in detail_df.columns
    assert "测试校区" not in detail_df.columns
