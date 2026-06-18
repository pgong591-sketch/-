"""Import-flow invariants that do not touch the real business database."""
import sqlite3
from pathlib import Path

import pandas as pd


def test_nullable_unique_indexes_block_duplicate_empty_keys():
    sql = Path("db/init.sql").read_text(encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.executescript(sql)

    checks = [
        (
            "account_balance",
            "INSERT INTO account_balance(company_code, period, account_code, account_name, assist_dimensions) "
            "VALUES ('c','202601','1001','cash', ?)",
        ),
        (
            "pl_detail",
            "INSERT INTO pl_detail(company_code, period, item_code, item_name, category, dept_code) "
            "VALUES ('c','202601','i','item','cat', ?)",
        ),
        (
            "non_subject_allocation",
            "INSERT INTO non_subject_allocation(company_code, period, cost_center, account_code) "
            "VALUES ('c','202601','cc', ?)",
        ),
    ]

    for table_name, statement in checks:
        conn.execute(statement, (None,))
        try:
            conn.execute(statement, ("",))
        except sqlite3.IntegrityError:
            continue
        raise AssertionError(f"{table_name} allowed duplicate NULL/empty unique key")

    conn.close()


def test_import_to_database_rolls_back_entire_batch_on_row_error():
    from src.db_connection import execute_sql, init_database
    from src.reports import import_to_database

    init_database()

    df = pd.DataFrame(
        [
            {
                "company_code": "C001",
                "period": "202601",
                "account_code": "1001",
                "account_name": "cash",
                "opening_balance": 0,
                "debit_amount": 0,
                "credit_amount": 0,
                "ending_balance": 0,
            },
            {
                "company_code": "C001",
                "period": "202601",
                "account_code": "1002",
                "account_name": "bank",
                "opening_balance": 0,
                "debit_amount": 0,
                "credit_amount": 0,
                "ending_balance": 0,
                "unexpected_column": "force row-level failure",
            },
        ]
    )

    result = import_to_database(
        df,
        "account_balance",
        "C001",
        "202601",
        "TEST_ROLLBACK",
        file_name="rollback.xlsx",
    )

    assert result["errors"]
    account_rows = execute_sql(
        "SELECT COUNT(*) AS cnt FROM account_balance WHERE import_batch = :batch",
        {"batch": "TEST_ROLLBACK"},
    ).iloc[0]["cnt"]
    log_rows = execute_sql(
        "SELECT COUNT(*) AS cnt FROM import_logs WHERE batch_no = :batch",
        {"batch": "TEST_ROLLBACK"},
    ).iloc[0]["cnt"]
    assert account_rows == 0
    assert log_rows == 0


def test_template_account_range_sums_duplicate_account_codes():
    from src.reports import _calculate_from_account_ranges

    balance_df = pd.DataFrame(
        [
            {"account_code": "1001", "ending_balance": 10.0, "debit_amount": 0, "credit_amount": 0},
            {"account_code": "1001", "ending_balance": 15.0, "debit_amount": 0, "credit_amount": 0},
            {"account_code": "1002", "ending_balance": 5.0, "debit_amount": 0, "credit_amount": 0},
        ]
    )
    balance_df = balance_df.groupby("account_code", as_index=True)[
        ["ending_balance", "debit_amount", "credit_amount"]
    ].sum()

    assert _calculate_from_account_ranges('[{"from":"1001"}]', balance_df) == 25.0
    assert _calculate_from_account_ranges('[{"from":"1001","to":"1002"}]', balance_df) == 30.0


def test_clean_df_preserves_missing_string_cells():
    from src.import_parser import BaseParser

    df = pd.DataFrame({"name": ["  cash  ", None], "amount": [1, 2]})
    cleaned = BaseParser()._clean_df(df)

    assert cleaned.loc[0, "name"] == "cash"
    assert pd.isna(cleaned.loc[1, "name"])
