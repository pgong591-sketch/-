"""Prepare a non-destructive restored finance database candidate.

The script copies the latest business backup into a separate candidate file,
then applies the schema and configuration rules that were added after the
backup was created.
"""

from __future__ import annotations

import argparse
import os
import runpy
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_cashflow_template import seed_cashflow_template
from src.company_aliases import seed_aliases_from_companies
from src.db_connection import init_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "finance_dw_backup_before_goodwill_20260521_172009.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "finance_dw_restore_candidate_20260523.db"
CURRENT_DB = PROJECT_ROOT / "data" / "finance_dw.db"
SQL_EXPR = "SQL表达式"


def sql_literal(value: object) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def parse_line_no(value: object, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def normalize_goodwill(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        UPDATE balance_sheet
        SET item_name = ?
        WHERE side = ?
          AND line_number = ?
          AND item_name <> ?
        """,
        ("商誉", "资产", "21", "商誉"),
    )
    conn.commit()
    return cur.rowcount


def seed_balance_sheet_template(conn: sqlite3.Connection, replace: bool = True) -> int:
    if replace:
        conn.execute("DELETE FROM balance_sheet_template")
    existing = conn.execute("SELECT COUNT(*) FROM balance_sheet_template").fetchone()[0]
    if existing:
        return 0

    rows = conn.execute(
        """
        SELECT
            side,
            line_number,
            item_name,
            MAX(COALESCE(is_subtotal, 0)) AS is_subtotal,
            MIN(COALESCE(sort_order, 0)) AS sort_order
        FROM balance_sheet
        GROUP BY side, line_number, item_name
        ORDER BY MIN(COALESCE(sort_order, 0)), CAST(line_number AS INTEGER), side, item_name
        """
    ).fetchall()

    inserted = 0
    for index, (side, line_number, item_name, is_subtotal, sort_order) in enumerate(rows, start=1):
        line_no = parse_line_no(line_number, index)
        line_predicate = "line_number IS NULL" if line_number is None else f"line_number = {sql_literal(line_number)}"
        sql_expression = (
            "SELECT COALESCE(SUM(ending_balance), 0) "
            "FROM balance_sheet "
            "WHERE company_code = :company "
            "AND period = :period "
            f"AND side = {sql_literal(side)} "
            f"AND item_name = {sql_literal(item_name)} "
            f"AND {line_predicate}"
        )
        conn.execute(
            """
            INSERT INTO balance_sheet_template
                (line_no, item_name, bs_category, is_subtotal, subtotal_group,
                 formula_type, account_ranges, sql_expression, indent_level,
                 is_bold, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, ?, ?)
            """,
            (
                line_no,
                item_name,
                side,
                int(is_subtotal or 0),
                f"{side}:{line_number}" if is_subtotal else None,
                SQL_EXPR,
                sql_expression,
                int(is_subtotal or 0),
                int(sort_order or index * 10),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def seed_income_statement_template(conn: sqlite3.Connection, replace: bool = True) -> int:
    if replace:
        conn.execute("DELETE FROM income_statement_template")
    existing = conn.execute("SELECT COUNT(*) FROM income_statement_template").fetchone()[0]
    if existing:
        return 0

    rows = conn.execute(
        """
        SELECT
            item_name,
            MIN(COALESCE(sort_order, 0)) AS sort_order
        FROM income_statement
        GROUP BY item_name
        ORDER BY MIN(COALESCE(sort_order, 0)), item_name
        """
    ).fetchall()

    inserted = 0
    for index, (item_name, sort_order) in enumerate(rows, start=1):
        is_subtotal = int(any(token in str(item_name) for token in ("小计", "合计", "利润")))
        sql_expression = (
            "SELECT COALESCE("
            "SUM(NULLIF(cumulative_value, 0)), "
            "SUM(period4_value), SUM(period3_value), SUM(period2_value), SUM(period1_value), 0"
            ") FROM income_statement "
            "WHERE company_code = :company "
            "AND period = :period "
            f"AND item_name = {sql_literal(item_name)}"
        )
        conn.execute(
            """
            INSERT INTO income_statement_template
                (line_no, item_name, is_subtotal, subtotal_group, formula_type,
                 account_ranges, sql_expression, sign, indent_level, is_bold, sort_order)
            VALUES (?, ?, ?, ?, ?, NULL, ?, '+', 0, ?, ?)
            """,
            (
                index,
                item_name,
                is_subtotal,
                f"income:{index}" if is_subtotal else None,
                SQL_EXPR,
                sql_expression,
                is_subtotal,
                int(sort_order or index * 10),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def migrate_legacy_aliases() -> tuple[int, int]:
    namespace = runpy.run_path(str(PROJECT_ROOT / "scripts" / "archive" / "migrate_aliases.py"))
    return namespace["migrate_aliases"]()


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def prepare_candidate(source: Path, output: Path, replace: bool = False) -> dict[str, int]:
    source = source.resolve()
    output = output.resolve()
    if output == CURRENT_DB.resolve():
        raise ValueError("Refusing to write restore candidate over data/finance_dw.db")
    if not source.exists():
        raise FileNotFoundError(source)
    if output.exists():
        if not replace:
            raise FileExistsError(f"{output} already exists; pass --replace to rebuild it")
        output.unlink()

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    os.environ["FINANCE_DW_DB_PATH"] = str(output)

    init_database()
    company_alias_seeded = seed_aliases_from_companies()
    legacy_alias_inserted, legacy_alias_skipped = migrate_legacy_aliases()
    cashflow_seeded = seed_cashflow_template(replace=True)

    conn = sqlite3.connect(output)
    try:
        goodwill_rows = normalize_goodwill(conn)
        balance_template_seeded = seed_balance_sheet_template(conn, replace=True)
        income_template_seeded = seed_income_statement_template(conn, replace=True)
        counts = {
            "companies": count_rows(conn, "companies"),
            "company_aliases": count_rows(conn, "company_aliases"),
            "account_balance": count_rows(conn, "account_balance"),
            "balance_sheet": count_rows(conn, "balance_sheet"),
            "income_statement": count_rows(conn, "income_statement"),
            "balance_sheet_template": count_rows(conn, "balance_sheet_template"),
            "income_statement_template": count_rows(conn, "income_statement_template"),
            "cashflow_template": count_rows(conn, "cashflow_template"),
            "goodwill_rows_normalized": goodwill_rows,
            "company_aliases_from_companies": company_alias_seeded,
            "legacy_aliases_inserted": legacy_alias_inserted,
            "legacy_aliases_skipped": legacy_alias_skipped,
            "cashflow_seeded": cashflow_seeded,
            "balance_template_seeded": balance_template_seeded,
            "income_template_seeded": income_template_seeded,
        }
        return counts
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    counts = prepare_candidate(args.source, args.output, replace=args.replace)
    print(f"restore candidate: {args.output}")
    for key, value in counts.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
