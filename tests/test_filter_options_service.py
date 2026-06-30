import pandas as pd
import pytest
from sqlalchemy import text

from src.db_connection import PROJECT_ROOT, get_db_path, get_session, init_database
from src.filter_options_service import (
    apply_internal_management_fee_elimination,
    get_consolidation_company_codes,
    get_report_company_scope,
    get_workspace_company_options,
    is_consolidation_node,
)


@pytest.fixture(autouse=True)
def isolated_filter_options_database(tmp_path, monkeypatch):
    db_path = tmp_path / "filter_options_test.db"
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(db_path))
    assert get_db_path() == db_path
    assert get_db_path() != PROJECT_ROOT / "data" / "finance_dw.db"


def _seed_filter_companies():
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
                ('1010102', '南城校区', '南城', '10101', 3, '/101/10101/1010102', 1, 1, 1),
                ('10199', '普通公司', '普通', '101', 2, '/101/10199', 1, 1, 1),
                ('10198', '非合并公司', '非合并', '101', 2, '/101/10198', 1, 0, 1)
        """))
        session.execute(text("""
            INSERT INTO dim_company
                (company_id, company_name, business_group, business_type, region, is_operational)
            VALUES
                ('101', '集团公司', '职能公司模块', '集团', '东莞', 0),
                ('10101', '合并节点', '非学科素质中心模块', '管理中心', '东莞', 1),
                ('1010101', '莞城校区', '非学科素质中心模块', '校区', '莞城', 1),
                ('1010102', '南城校区', '国际教育模块', '校区', '南城', 1),
                ('10199', '普通公司', '职能公司模块', '公司', '深圳', 1),
                ('10198', '非合并公司', '职能公司模块', '公司', '深圳', 1)
        """))
        session.commit()
    finally:
        session.close()


def test_report_scope_keeps_101_as_own_company_only():
    _seed_filter_companies()

    assert is_consolidation_node("101") is False
    assert get_report_company_scope(["101"]) == ["101"]


def test_report_scope_supports_group_code_1_and_consolidation_nodes():
    _seed_filter_companies()

    assert get_report_company_scope(["1"]) == ["101", "10101", "1010101", "1010102", "10199"]
    assert get_consolidation_company_codes("10101") == ["10101", "1010101", "1010102"]
    assert get_report_company_scope(["10199"]) == ["10199"]


def test_default_and_group_scope_exclude_non_consolidated_companies():
    _seed_filter_companies()

    assert "10198" not in get_report_company_scope([])
    assert "10198" not in get_report_company_scope(["1"])


def test_direct_non_consolidated_company_selection_is_rejected():
    _seed_filter_companies()

    assert get_report_company_scope(["10198"]) == []


def test_report_scope_applies_dimension_intersection_and_dedupes_codes():
    _seed_filter_companies()

    assert get_report_company_scope(
        ["10101", "10101"],
        business_group="非学科素质中心模块",
        business_type="校区",
        region="莞城",
    ) == ["1010101"]


def test_workspace_company_options_include_group_scope_without_dimension_filters():
    _seed_filter_companies()

    df = get_workspace_company_options()
    assert df.iloc[0]["code"] == "1"
    assert df.iloc[0]["name"] == "集团"
    assert "10198" not in df["code"].tolist()

    filtered = get_workspace_company_options(business_group="非学科素质中心模块")
    assert "1" not in filtered["code"].tolist()


def test_internal_management_fee_elimination_offsets_parent_revenue():
    _seed_filter_companies()
    source_df = pd.DataFrame(
        [
            ("10101", "合并节点", "OPERATING_012_收入合计", "收入合计", 1000.0, 5000.0),
            ("10101", "合并节点", "DETAIL_主营业务收入", "主营业务收入", 1000.0, 5000.0),
            ("1010101", "莞城校区", "DETAIL_管理费服务费", "管理费服务费", 120.0, 300.0),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount"],
    )

    adjusted = apply_internal_management_fee_elimination(source_df, ["10101", "1010101"])

    revenue_total = adjusted.loc[adjusted["source_item_name"] == "收入合计", "current_amount"].iloc[0]
    revenue_ytd_total = adjusted.loc[adjusted["source_item_name"] == "收入合计", "ytd_amount"].iloc[0]
    operating_revenue = adjusted.loc[adjusted["source_item_name"] == "主营业务收入", "current_amount"].iloc[0]
    management_fee = adjusted.loc[adjusted["source_item_name"] == "管理费服务费", "current_amount"].iloc[0]
    assert revenue_total == 880.0
    assert revenue_ytd_total == 4700.0
    assert operating_revenue == 1000.0
    assert management_fee == 120.0


def test_internal_management_fee_elimination_blank_ytd_falls_back_to_current():
    _seed_filter_companies()
    source_df = pd.DataFrame(
        [
            ("10101", "合并节点", "OPERATING_012_收入合计", "收入合计", 1000.0, ""),
            ("1010101", "莞城校区", "DETAIL_管理费服务费", "管理费服务费", 120.0, "   "),
        ],
        columns=["company_code", "company_name", "account_code", "source_item_name", "current_amount", "ytd_amount"],
    )

    adjusted = apply_internal_management_fee_elimination(source_df, ["10101", "1010101"])

    revenue_total = adjusted.loc[adjusted["source_item_name"] == "收入合计", "current_amount"].iloc[0]
    revenue_ytd_total = adjusted.loc[adjusted["source_item_name"] == "收入合计", "ytd_amount"].iloc[0]
    assert revenue_total == 880.0
    assert revenue_ytd_total == 880.0
