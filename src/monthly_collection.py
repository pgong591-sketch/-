"""Monthly financial data collection tracking.

This module keeps the first closed-loop MVP intentionally small:
requirements define what should be collected, and status is recalculated from
``import_logs`` whenever the user refreshes a period.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import text

from .db_connection import execute_sql, get_session
from .report_types import REPORT_TYPE_TABLE_MAP


TABLE_TO_REPORT_TYPE = {}
for report_type, table_name in REPORT_TYPE_TABLE_MAP.items():
    TABLE_TO_REPORT_TYPE.setdefault(table_name, report_type)


REQUIRED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS monthly_collection_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL,
    company_code    TEXT NOT NULL,
    report_type     TEXT NOT NULL,
    required        INTEGER DEFAULT 1,
    due_date        TEXT,
    remark          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period, company_code, report_type)
)
"""

STATUS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS monthly_collection_status (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    period                TEXT NOT NULL,
    company_code          TEXT NOT NULL,
    report_type           TEXT NOT NULL,
    status                TEXT DEFAULT '缺失',
    latest_batch_no       TEXT,
    latest_file_name      TEXT,
    latest_import_time    TEXT,
    total_success_batches INTEGER DEFAULT 0,
    total_error_batches   INTEGER DEFAULT 0,
    issue_detail          TEXT,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period, company_code, report_type)
)
"""


def _normalize_report_types(report_types: Iterable[str]) -> list[str]:
    return [str(item).strip() for item in report_types if str(item).strip()]


def _to_log_report_type(report_type: str) -> str:
    """Return the report_type value used by import_logs."""
    clean = str(report_type).strip()
    return REPORT_TYPE_TABLE_MAP.get(clean, clean)


def _to_display_report_type(report_type: str) -> str:
    """Return the Chinese report type used by collection requirements."""
    clean = str(report_type).strip()
    return TABLE_TO_REPORT_TYPE.get(clean, clean)


def ensure_monthly_collection_schema() -> None:
    """Ensure monthly collection tables and indexes exist."""
    session = get_session()
    try:
        session.execute(text(REQUIRED_TABLE_SQL))
        session.execute(text(STATUS_TABLE_SQL))
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monthly_collection_requirements_period "
                "ON monthly_collection_requirements(period)"
            )
        )
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monthly_collection_status_period "
                "ON monthly_collection_status(period)"
            )
        )
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monthly_collection_status_status "
                "ON monthly_collection_status(status)"
            )
        )
        session.commit()
    finally:
        session.close()


def seed_requirements_from_active_companies(period: str, report_types: list[str]) -> int:
    """Create required collection rows for active companies and report types."""
    ensure_monthly_collection_schema()
    clean_period = str(period).strip()
    clean_types = [_to_display_report_type(item) for item in _normalize_report_types(report_types)]
    if not clean_period or not clean_types:
        return 0

    companies = execute_sql(
        """
        SELECT code
        FROM companies
        WHERE status = 1
        ORDER BY code
        """
    )
    if len(companies) == 0:
        return 0

    inserted = 0
    session = get_session()
    try:
        for company_code in companies["code"].astype(str).tolist():
            for report_type in clean_types:
                result = session.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO monthly_collection_requirements
                            (period, company_code, report_type, required, updated_at)
                        VALUES
                            (:period, :company_code, :report_type, 1, CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "period": clean_period,
                        "company_code": company_code,
                        "report_type": report_type,
                    },
                )
                inserted += int(result.rowcount or 0)
        session.commit()
    finally:
        session.close()

    return inserted


def _status_from_counts(success_count: int, error_count: int) -> tuple[str, str]:
    if success_count >= 2:
        return "重复", f"成功导入 {success_count} 次，请确认是否需要保留多批次。"
    if success_count == 1:
        return "已收集", ""
    if error_count > 0:
        return "异常", f"存在 {error_count} 次失败导入，尚无成功入库。"
    return "缺失", "未找到成功导入记录。"


def refresh_collection_status(period: str) -> int:
    """Recalculate collection status for a period from import_logs."""
    ensure_monthly_collection_schema()
    clean_period = str(period).strip()
    if not clean_period:
        return 0

    requirements = execute_sql(
        """
        SELECT period, company_code, report_type
        FROM monthly_collection_requirements
        WHERE period = :period AND COALESCE(required, 1) = 1
        ORDER BY company_code, report_type
        """,
        {"period": clean_period},
    )
    if len(requirements) == 0:
        return 0

    log_summary = execute_sql(
        """
        WITH ranked_logs AS (
            SELECT
                company_code,
                report_type,
                batch_no,
                file_name,
                created_at,
                status,
                ROW_NUMBER() OVER (
                    PARTITION BY company_code, report_type
                    ORDER BY created_at DESC, id DESC
                ) AS rn
            FROM import_logs
            WHERE period = :period
        )
        SELECT
            company_code,
            report_type,
            SUM(CASE WHEN status = '成功' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status = '失败' THEN 1 ELSE 0 END) AS error_count,
            MAX(CASE WHEN rn = 1 THEN batch_no END) AS latest_batch_no,
            MAX(CASE WHEN rn = 1 THEN file_name END) AS latest_file_name,
            MAX(CASE WHEN rn = 1 THEN created_at END) AS latest_import_time
        FROM ranked_logs
        GROUP BY company_code, report_type
        """,
        {"period": clean_period},
    )
    summary_map: dict[tuple[str, str], dict] = {}
    for _, row in log_summary.iterrows():
        company_code = str(row["company_code"])
        report_key = _to_log_report_type(str(row["report_type"]))
        key = (company_code, report_key)
        item = row.to_dict()
        item["success_count"] = 0 if pd.isna(item["success_count"]) else int(item["success_count"])
        item["error_count"] = 0 if pd.isna(item["error_count"]) else int(item["error_count"])
        if key in summary_map:
            summary_map[key]["success_count"] += item["success_count"]
            summary_map[key]["error_count"] += item["error_count"]
        else:
            summary_map[key] = item

    updated = 0
    session = get_session()
    try:
        for _, requirement in requirements.iterrows():
            company_code = str(requirement["company_code"])
            report_type = _to_display_report_type(str(requirement["report_type"]))
            log_report_type = _to_log_report_type(report_type)
            row = summary_map.get((company_code, log_report_type))
            success_count = int(row["success_count"]) if row is not None and not pd.isna(row["success_count"]) else 0
            error_count = int(row["error_count"]) if row is not None and not pd.isna(row["error_count"]) else 0
            status, detail = _status_from_counts(success_count, error_count)
            latest_batch_no = "" if row is None or pd.isna(row["latest_batch_no"]) else str(row["latest_batch_no"])
            latest_file_name = "" if row is None or pd.isna(row["latest_file_name"]) else str(row["latest_file_name"])
            latest_import_time = "" if row is None or pd.isna(row["latest_import_time"]) else str(row["latest_import_time"])
            session.execute(
                text(
                    """
                    INSERT INTO monthly_collection_status (
                        period, company_code, report_type, status,
                        latest_batch_no, latest_file_name, latest_import_time,
                        total_success_batches, total_error_batches,
                        issue_detail, updated_at
                    )
                    VALUES (
                        :period, :company_code, :report_type, :status,
                        :latest_batch_no, :latest_file_name, :latest_import_time,
                        :total_success_batches, :total_error_batches,
                        :issue_detail, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(period, company_code, report_type) DO UPDATE SET
                        status = excluded.status,
                        latest_batch_no = excluded.latest_batch_no,
                        latest_file_name = excluded.latest_file_name,
                        latest_import_time = excluded.latest_import_time,
                        total_success_batches = excluded.total_success_batches,
                        total_error_batches = excluded.total_error_batches,
                        issue_detail = excluded.issue_detail,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "period": clean_period,
                    "company_code": company_code,
                    "report_type": report_type,
                    "status": status,
                    "latest_batch_no": latest_batch_no,
                    "latest_file_name": latest_file_name,
                    "latest_import_time": latest_import_time,
                    "total_success_batches": success_count,
                    "total_error_batches": error_count,
                    "issue_detail": detail,
                },
            )
            updated += 1
        session.commit()
    finally:
        session.close()

    return updated


def get_collection_matrix(period: str) -> pd.DataFrame:
    """Return a company-by-report-type status matrix for the selected period."""
    ensure_monthly_collection_schema()
    clean_period = str(period).strip()
    if not clean_period:
        return pd.DataFrame()

    rows = execute_sql(
        """
        SELECT
            r.company_code AS 公司编码,
            COALESCE(c.name, r.company_code) AS 公司名称,
            r.report_type AS 报表类型,
            COALESCE(s.status, '缺失') AS 收集状态
        FROM monthly_collection_requirements r
        LEFT JOIN monthly_collection_status s
          ON s.period = r.period
         AND s.company_code = r.company_code
         AND s.report_type = r.report_type
        LEFT JOIN companies c ON c.code = r.company_code
        WHERE r.period = :period AND COALESCE(r.required, 1) = 1
        ORDER BY r.company_code, r.report_type
        """,
        {"period": clean_period},
    )
    if len(rows) == 0:
        return pd.DataFrame()
    matrix = rows.pivot_table(
        index=["公司编码", "公司名称"],
        columns="报表类型",
        values="收集状态",
        aggfunc="first",
    ).reset_index()
    matrix.columns.name = None
    return matrix


def get_collection_missing(period: str) -> pd.DataFrame:
    """Return missing, duplicate, and error details for a period."""
    ensure_monthly_collection_schema()
    clean_period = str(period).strip()
    if not clean_period:
        return pd.DataFrame()
    return execute_sql(
        """
        SELECT
            s.company_code AS 公司编码,
            COALESCE(c.name, s.company_code) AS 公司名称,
            s.report_type AS 报表类型,
            s.status AS 收集状态,
            s.total_success_batches AS 成功批次数,
            s.total_error_batches AS 失败批次数,
            s.latest_batch_no AS 最新批次号,
            s.latest_file_name AS 最新文件名,
            s.latest_import_time AS 最新导入时间,
            s.issue_detail AS 问题说明
        FROM monthly_collection_status s
        LEFT JOIN companies c ON c.code = s.company_code
        WHERE s.period = :period
          AND s.status IN ('缺失', '重复', '异常')
        ORDER BY
            CASE s.status
                WHEN '异常' THEN 1
                WHEN '重复' THEN 2
                WHEN '缺失' THEN 3
                ELSE 9
            END,
            s.company_code,
            s.report_type
        """,
        {"period": clean_period},
    )
