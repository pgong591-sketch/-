import pandas as pd
from sqlalchemy import text

from src.db_connection import get_session, init_database, table_exists
from src.monthly_collection import (
    ensure_monthly_collection_schema,
    get_collection_matrix,
    get_collection_missing,
    refresh_collection_status,
    seed_requirements_from_active_companies,
)


PERIOD = "202603"


def _setup_db() -> None:
    init_database()
    ensure_monthly_collection_schema()
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO companies (code, name, status, is_consolidated)
                VALUES
                    ('C001', '一号公司', 1, 1),
                    ('C002', '二号公司', 1, 1),
                    ('C999', '停用公司', 0, 1)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _insert_import_log(
    *,
    company_code: str,
    report_type: str,
    status: str,
    batch_no: str,
) -> None:
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO import_logs (
                    batch_no, company_code, period, report_type,
                    file_name, status, total_rows, success_rows, error_rows
                )
                VALUES (
                    :batch_no, :company_code, :period, :report_type,
                    :file_name, :status, 10, :success_rows, :error_rows
                )
                """
            ),
            {
                "batch_no": batch_no,
                "company_code": company_code,
                "period": PERIOD,
                "report_type": report_type,
                "file_name": f"{batch_no}.xlsx",
                "status": status,
                "success_rows": 10 if status == "成功" else 0,
                "error_rows": 0 if status == "成功" else 10,
            },
        )
        session.commit()
    finally:
        session.close()


def _matrix_status(matrix: pd.DataFrame, company_code: str, report_type: str) -> str:
    row = matrix[matrix["公司编码"] == company_code]
    assert len(row) == 1
    return str(row.iloc[0][report_type])


def test_monthly_collection_tables_are_created():
    init_database()
    ensure_monthly_collection_schema()

    assert table_exists("monthly_collection_requirements")
    assert table_exists("monthly_collection_status")


def test_seed_requirements_from_active_companies():
    _setup_db()

    created = seed_requirements_from_active_companies(PERIOD, ["科目余额表", "资产负债表"])

    assert created == 4
    matrix = get_collection_matrix(PERIOD)
    assert len(matrix) == 2
    assert {"公司编码", "公司名称", "科目余额表", "资产负债表"}.issubset(matrix.columns)


def test_refresh_marks_missing_when_no_success_import():
    _setup_db()
    seed_requirements_from_active_companies(PERIOD, ["科目余额表"])

    refreshed = refresh_collection_status(PERIOD)

    assert refreshed == 2
    matrix = get_collection_matrix(PERIOD)
    assert _matrix_status(matrix, "C001", "科目余额表") == "缺失"
    missing = get_collection_missing(PERIOD)
    assert set(missing["收集状态"]) == {"缺失"}


def test_refresh_marks_collected_with_one_success_import():
    _setup_db()
    seed_requirements_from_active_companies(PERIOD, ["科目余额表"])
    _insert_import_log(company_code="C001", report_type="科目余额表", status="成功", batch_no="B001")

    refresh_collection_status(PERIOD)

    matrix = get_collection_matrix(PERIOD)
    assert _matrix_status(matrix, "C001", "科目余额表") == "已收集"
    assert _matrix_status(matrix, "C002", "科目余额表") == "缺失"


def test_refresh_matches_chinese_requirement_with_import_log_table_name():
    _setup_db()
    seed_requirements_from_active_companies(PERIOD, ["科目余额表"])
    _insert_import_log(company_code="C001", report_type="account_balance", status="成功", batch_no="B001")

    refresh_collection_status(PERIOD)

    matrix = get_collection_matrix(PERIOD)
    assert _matrix_status(matrix, "C001", "科目余额表") == "已收集"


def test_refresh_marks_duplicate_with_multiple_success_imports():
    _setup_db()
    seed_requirements_from_active_companies(PERIOD, ["科目余额表"])
    _insert_import_log(company_code="C001", report_type="科目余额表", status="成功", batch_no="B001")
    _insert_import_log(company_code="C001", report_type="科目余额表", status="成功", batch_no="B002")

    refresh_collection_status(PERIOD)

    matrix = get_collection_matrix(PERIOD)
    assert _matrix_status(matrix, "C001", "科目余额表") == "重复"
    issues = get_collection_missing(PERIOD)
    duplicate = issues[(issues["公司编码"] == "C001") & (issues["报表类型"] == "科目余额表")]
    assert duplicate.iloc[0]["收集状态"] == "重复"
    assert int(duplicate.iloc[0]["成功批次数"]) == 2


def test_refresh_marks_exception_with_failure_and_no_success():
    _setup_db()
    seed_requirements_from_active_companies(PERIOD, ["损益表"])
    _insert_import_log(company_code="C002", report_type="损益表", status="失败", batch_no="B_ERR")

    refresh_collection_status(PERIOD)

    matrix = get_collection_matrix(PERIOD)
    assert _matrix_status(matrix, "C002", "损益表") == "异常"
    issues = get_collection_missing(PERIOD)
    error = issues[(issues["公司编码"] == "C002") & (issues["报表类型"] == "损益表")]
    assert error.iloc[0]["收集状态"] == "异常"
    assert int(error.iloc[0]["失败批次数"]) == 1
