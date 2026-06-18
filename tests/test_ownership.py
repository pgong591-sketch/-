import pandas as pd
from sqlalchemy import text

from src.db_connection import execute_sql, get_session, init_database
from src.ownership import (
    classify_investment,
    get_ownership_grid,
    prune_ownership_orphans,
    save_ownership_grid,
    seed_ownership_from_companies,
)


def test_seed_ownership_from_company_hierarchy():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, status)
            VALUES
                ('ROOT', '多维教育集团', '集团', NULL, 0, '/ROOT', 1),
                ('101', '广东多维教育科技集团有限公司', '集团公司', 'ROOT', 1, '/ROOT/101', 1),
                ('10101', '多维培优', '多维培优', '101', 2, '/ROOT/101/10101', 1),
                ('1010101', '东莞非学科管理中心', '非学科管理中心', '10101', 3, '/ROOT/101/10101/1010101', 1)
        """))
        session.commit()
    finally:
        session.close()

    inserted = seed_ownership_from_companies()
    assert inserted == 2

    grid = get_ownership_grid()
    assert set(grid["parent_code"]) == {"101", "10101"}
    assert "ROOT" not in set(grid["parent_code"])
    assert set(grid["investment_category"]) == {"全资子公司"}


def test_save_ownership_grid_allows_partial_investment():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, status)
            VALUES
                ('101', '广东多维教育科技集团有限公司', '集团公司', NULL, 1, '/101', 1),
                ('102', '深圳尔遇教育科技有限公司', '深圳尔遇', '101', 2, '/101/102', 1)
        """))
        session.commit()
    finally:
        session.close()

    edited = pd.DataFrame([{
        "母公司编码": "101",
        "子公司编码": "102",
        "投资占比(%)": 49,
        "生效日期": "2026-01-01",
        "失效日期": "",
        "是否控制": "否",
    }])

    saved = save_ownership_grid(edited)
    assert saved == 1

    rows = execute_sql("SELECT parent_code, sub_code, ownership_pct, effective_date, is_control FROM ownership")
    assert rows.iloc[0]["parent_code"] == "101"
    assert rows.iloc[0]["sub_code"] == "102"
    assert rows.iloc[0]["ownership_pct"] == 49
    assert rows.iloc[0]["effective_date"] == "20260101"
    assert rows.iloc[0]["is_control"] == 0
    assert classify_investment(49, 0) == "参股公司"


def test_ownership_grid_prunes_deleted_company_rows():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, status)
            VALUES
                ('101', '集团公司', '集团公司', NULL, 1, '/101', 1),
                ('102', '待删除公司', '待删除公司', '101', 2, '/101/102', 1)
        """))
        session.execute(text("""
            INSERT INTO ownership
                (parent_code, sub_code, ownership_pct, effective_date, is_control)
            VALUES
                ('101', '102', 100, '20260101', 1)
        """))
        session.execute(text("DELETE FROM companies WHERE code = '102'"))
        session.commit()
    finally:
        session.close()

    assert prune_ownership_orphans() == 1
    grid = get_ownership_grid()
    assert "102" not in grid["sub_code"].tolist()
