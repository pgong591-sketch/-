import pandas as pd
from sqlalchemy import text

from src.base_settings_service import (
    COMPANY_HIERARCHY_ROOT_CODE,
    build_company_hierarchy_graph_data,
    detect_company_hierarchy_issues,
    get_base_health_checks,
    get_base_settings_overview,
    get_business_group_options,
    get_company_hierarchy_children_map,
    get_company_dimension,
    get_company_options,
    get_company_scope_codes,
    get_default_expanded_company_codes,
    normalize_business_group,
    normalize_operating_item,
    record_import_issue,
    resolve_company_identity,
)
from src.db_connection import execute_sql, get_session, init_database


def _seed_company_master():
    init_database()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path,
                 is_consolidated, status)
            VALUES
                ('101', '集团公司', '集团', NULL, 1, '/101', 1, 1),
                ('10101', '非学科管理中心', '非学科', '101', 2, '/101/10101', 1, 1),
                ('1010101', '莞城校区', '莞城', '10101', 3, '/101/10101/1010101', 1, 1),
                ('102', '停用公司', '停用', NULL, 1, '/102', 1, 0)
        """))
        session.execute(text("""
            INSERT OR REPLACE INTO dim_company
                (company_id, company_name, business_group, business_type, region, is_operational)
            VALUES
                ('101', '集团公司', '职能公司模块', '集团', '东莞', 0),
                ('10101', '非学科管理中心', '非学科素质中心模块', '管理中心', '东莞', 1),
                ('1010101', '莞城校区', '非学科素质中心模块', '校区', '莞城', 1)
        """))
        session.execute(text("""
            INSERT OR REPLACE INTO company_aliases (alias, company_code, source, status)
            VALUES ('莞城简称', '1010101', 'manual', 1)
        """))
        session.commit()
    finally:
        session.close()


def test_company_options_and_scope_codes_use_existing_master_data():
    _seed_company_master()

    options = get_company_options()
    assert [item["company_code"] for item in options] == ["101", "10101", "1010101"]
    assert options[-1]["business_group"] == "非学科素质中心模块"

    assert get_company_scope_codes("10101") == ["10101", "1010101"]
    assert get_company_scope_codes("10101", include_descendants=False) == ["10101"]


def test_resolve_company_identity_exact_and_fuzzy_suggestions_do_not_write_aliases():
    _seed_company_master()
    before = execute_sql("SELECT COUNT(*) AS cnt FROM company_aliases").iloc[0]["cnt"]

    exact = resolve_company_identity("莞城简称")
    fuzzy = resolve_company_identity("莞城校", mode="fuzzy")
    strict = resolve_company_identity("莞城校", mode="strict")

    after = execute_sql("SELECT COUNT(*) AS cnt FROM company_aliases").iloc[0]["cnt"]
    assert exact["ok"] is True
    assert exact["company_code"] == "1010101"
    assert fuzzy["ok"] is False
    assert fuzzy["suggestions"][0]["company_code"] == "1010101"
    assert strict["suggestions"] == []
    assert after == before


def test_dimensions_and_normalizers():
    _seed_company_master()

    dimension = get_company_dimension("1010101")
    assert dimension["business_group"] == "非学科素质中心模块"
    assert normalize_business_group("素质板块") == "非学科素质中心模块"
    assert normalize_operating_item("差旅交际费") == "交际费"
    assert "非学科素质中心模块" in get_business_group_options()


def test_base_overview_health_checks_and_import_issue_recording():
    _seed_company_master()

    overview = get_base_settings_overview()
    checks = {item["check_key"]: item for item in get_base_health_checks()}
    missing = record_import_issue(
        batch_no="B1",
        company_code="1010101",
        issue_type="company",
        issue_message="missing table",
    )

    assert overview["company_count"] == 3
    assert overview["alias_count"] == 1
    assert overview["dimension_count"] == 3
    assert overview["ungrouped_company_count"] == 0
    assert overview["alias_conflict_count"] == 0
    assert overview["unresolved_company_name_count"] is None
    assert overview["missing_dimension_count"] == 0
    assert overview["tree_path_issue_count"] == 0
    assert overview["import_issue_pool_available"] is False
    assert overview["change_log_available"] is False
    assert checks["dimension_orphans"]["count"] == 0
    assert missing == {"recorded": False, "reason": "missing_import_issue_pool"}

    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE import_issue_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_no TEXT,
                company_code TEXT,
                issue_type TEXT,
                issue_message TEXT,
                severity TEXT,
                status TEXT,
                extra TEXT
            )
        """))
        session.commit()
    finally:
        session.close()

    recorded = record_import_issue(
        batch_no="B1",
        company_code="1010101",
        issue_type="company",
        issue_message="cannot resolve",
        extra={"raw": "莞城"},
    )
    rows = execute_sql("SELECT batch_no, company_code, issue_message FROM import_issue_pool")
    refreshed_overview = get_base_settings_overview()

    assert recorded["recorded"] is True
    assert refreshed_overview["import_issue_pool_available"] is True
    assert refreshed_overview["unresolved_company_name_count"] == 1
    assert rows.to_dict("records") == [
        {"batch_no": "B1", "company_code": "1010101", "issue_message": "cannot resolve"}
    ]


def test_unresolved_company_count_is_pending_when_issue_message_column_missing():
    _seed_company_master()
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE import_issue_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_type TEXT,
                status TEXT
            )
        """))
        session.execute(text("""
            INSERT INTO import_issue_pool (issue_type, status)
            VALUES ('company', 'open')
        """))
        session.commit()
    finally:
        session.close()

    overview = get_base_settings_overview()

    assert overview["import_issue_pool_available"] is True
    assert overview["unresolved_company_name_count"] is None


def test_unresolved_company_count_is_pending_when_issue_type_column_missing():
    _seed_company_master()
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE import_issue_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_message TEXT,
                status TEXT
            )
        """))
        session.execute(text("""
            INSERT INTO import_issue_pool (issue_message, status)
            VALUES ('未识别公司', 'open')
        """))
        session.commit()
    finally:
        session.close()

    overview = get_base_settings_overview()

    assert overview["import_issue_pool_available"] is True
    assert overview["unresolved_company_name_count"] is None


def test_company_hierarchy_graph_builds_children_map_and_default_expansion():
    _seed_company_master()

    graph = build_company_hierarchy_graph_data()
    children_map = get_company_hierarchy_children_map(graph)
    expanded = get_default_expanded_company_codes(graph_data=graph)

    assert graph["root_code"] == COMPANY_HIERARCHY_ROOT_CODE
    assert COMPANY_HIERARCHY_ROOT_CODE in graph["nodes"]
    assert children_map[COMPANY_HIERARCHY_ROOT_CODE] == ["101", "102"]
    assert children_map["101"] == ["10101"]
    assert children_map["10101"] == ["1010101"]
    assert COMPANY_HIERARCHY_ROOT_CODE in expanded
    assert "101" in expanded
    assert "10101" in expanded


def test_company_hierarchy_graph_marks_inactive_and_consolidated_nodes():
    _seed_company_master()

    graph = build_company_hierarchy_graph_data()

    assert graph["nodes"]["102"]["status_label"] == "停用"
    assert graph["nodes"]["102"]["status"] == 0
    assert graph["nodes"]["101"]["is_consolidated"] == 1
    assert graph["nodes"]["101"]["consolidated_label"] == "合并"


def test_company_hierarchy_issues_detect_missing_parent_and_cycles_without_recursion():
    _seed_company_master()
    session = get_session()
    try:
        session.execute(text("""
            INSERT OR REPLACE INTO companies
                (code, name, short_name, parent_code, level, tree_path, is_consolidated, status)
            VALUES
                ('201', '缺失上级公司', '缺失上级', '999', 2, '/999/201', 1, 1),
                ('301', '循环公司A', '循环A', '302', 2, '/301', 1, 1),
                ('302', '循环公司B', '循环B', '301', 3, '/302', 1, 1)
        """))
        session.commit()
    finally:
        session.close()

    issues = detect_company_hierarchy_issues()
    graph = build_company_hierarchy_graph_data()
    issue_types = {(item["company_code"], item["issue_type"]) for item in issues}

    assert ("201", "missing_parent") in issue_types
    assert ("301", "cycle") in issue_types
    assert ("302", "cycle") in issue_types
    assert "201" in graph["children_map"][COMPANY_HIERARCHY_ROOT_CODE]
    assert "301" in graph["children_map"][COMPANY_HIERARCHY_ROOT_CODE]
    assert "302" in graph["children_map"][COMPANY_HIERARCHY_ROOT_CODE]
    assert graph["nodes"]["201"]["issue_label"] == "未挂接"
    assert graph["nodes"]["301"]["issue_label"] == "异常"


def test_company_hierarchy_graph_is_read_only_for_companies_and_dimensions():
    _seed_company_master()
    before_companies = execute_sql(
        "SELECT code, name, parent_code, level, tree_path, is_consolidated, status FROM companies ORDER BY code"
    ).to_dict("records")
    before_dimensions = execute_sql(
        "SELECT company_id, business_group FROM dim_company ORDER BY company_id"
    ).to_dict("records")

    graph = build_company_hierarchy_graph_data()
    issues = detect_company_hierarchy_issues()
    expanded = get_default_expanded_company_codes(graph_data=graph)

    after_companies = execute_sql(
        "SELECT code, name, parent_code, level, tree_path, is_consolidated, status FROM companies ORDER BY code"
    ).to_dict("records")
    after_dimensions = execute_sql(
        "SELECT company_id, business_group FROM dim_company ORDER BY company_id"
    ).to_dict("records")

    assert graph["nodes"]["101"]["display_name"] == "集团"
    assert issues == []
    assert expanded
    assert after_companies == before_companies
    assert after_dimensions == before_dimensions
