import pytest
from sqlalchemy import text

import app
from src.db_connection import PROJECT_ROOT, get_db_path, get_session, init_database


@pytest.fixture(autouse=True)
def isolated_workspace_filter_database(tmp_path, monkeypatch):
    db_path = tmp_path / "workspace_filter_test.db"
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(db_path))
    assert get_db_path() == db_path
    assert get_db_path() != PROJECT_ROOT / "data" / "finance_dw.db"


def _seed_workspace_scope():
    init_database()
    session = get_session()
    try:
        session.execute(text("DELETE FROM dim_company"))
        session.execute(text("DELETE FROM companies"))
        session.execute(text("""
            INSERT INTO companies
                (code, name, short_name, parent_code, level, tree_path, is_leaf, is_consolidated, status)
            VALUES
                ('101', '集团公司', '集团', NULL, 1, '/101', 0, 1, 1),
                ('10101', '合并节点', '合并', '101', 2, '/101/10101', 0, 1, 1),
                ('1010101', '莞城校区', '莞城', '10101', 3, '/101/10101/1010101', 1, 1, 1),
                ('1010102', '南城校区', '南城', '10101', 3, '/101/10101/1010102', 1, 1, 1)
        """))
        session.execute(text("""
            INSERT INTO dim_company
                (company_id, company_name, business_group, business_type, region, is_operational)
            VALUES
                ('101', '集团公司', '职能公司模块', '集团', '东莞', 0),
                ('10101', '合并节点', '非学科素质中心模块', '管理中心', '东莞', 1),
                ('1010101', '莞城校区', '非学科素质中心模块', '校区', '莞城', 1),
                ('1010102', '南城校区', '国际教育模块', '校区', '南城', 1)
        """))
        session.commit()
    finally:
        session.close()


def test_workspace_filter_selecting_101_does_not_expand_children():
    _seed_workspace_scope()

    filters = {
        "selected_company_codes": ["101"],
        "business_group": "不限",
        "business_type": "不限",
        "region": "不限",
    }

    assert app._resolve_filter_company_codes(filters) == ["101"]


def test_workspace_filter_selected_company_and_dimensions_use_intersection():
    _seed_workspace_scope()

    filters = {
        "selected_company_codes": ["10101"],
        "business_group": "非学科素质中心模块",
        "business_type": "校区",
        "region": "莞城",
    }

    assert app._resolve_filter_company_codes(filters) == ["1010101"]
