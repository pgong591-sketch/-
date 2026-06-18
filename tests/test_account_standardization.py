from sqlalchemy import text

from src.account_standardization import (
    ensure_account_standardization_schema,
    find_unmapped_accounts,
    get_account_mappings,
    get_mapping_coverage,
    get_standard_accounts,
    suggest_account_mappings,
    upsert_account_mapping,
    upsert_standard_account,
)
from src.db_connection import get_session, init_database


PERIOD = "202603"


def _setup_db() -> None:
    init_database()
    ensure_account_standardization_schema()
    session = get_session()
    try:
        session.execute(
            text(
                """
                INSERT INTO companies (code, name, status)
                VALUES ('C001', '一号公司', 1), ('C002', '二号公司', 1)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO account_balance (
                    company_code, period, account_code, account_name,
                    opening_balance, debit_amount, credit_amount, ending_balance
                )
                VALUES
                    ('C001', :period, '1001', '银行存款', 0, 0, 0, 100),
                    ('C001', :period, '6001', '主营业务收入', 0, 0, 0, 200),
                    ('C002', :period, '1001', '银行存款', 0, 0, 0, 300)
                """
            ),
            {"period": PERIOD},
        )
        session.commit()
    finally:
        session.close()


def test_standard_accounts_can_be_upserted_and_read():
    _setup_db()

    upsert_standard_account(
        {
            "标准科目编码": "1001",
            "标准科目名称": "货币资金",
            "科目类别": "资产",
            "余额方向": "借",
        }
    )

    df = get_standard_accounts()
    assert len(df) == 1
    assert df.iloc[0]["标准科目编码"] == "1001"
    assert df.iloc[0]["标准科目名称"] == "货币资金"


def test_account_mapping_can_be_upserted_and_read():
    _setup_db()
    upsert_standard_account({"标准科目编码": "1001", "标准科目名称": "货币资金", "科目类别": "资产"})

    upsert_account_mapping(
        {
            "公司编码": "C001",
            "原始科目编码": "1001",
            "原始科目名称": "银行存款",
            "标准科目编码": "1001",
        }
    )

    df = get_account_mappings("C001")
    assert len(df) == 1
    assert df.iloc[0]["原始科目编码"] == "1001"
    assert df.iloc[0]["标准科目名称"] == "货币资金"


def test_find_unmapped_accounts_respects_company_mapping():
    _setup_db()
    upsert_standard_account({"标准科目编码": "1001", "标准科目名称": "货币资金", "科目类别": "资产"})
    upsert_account_mapping({"公司编码": "C001", "原始科目编码": "1001", "标准科目编码": "1001"})

    unmapped = find_unmapped_accounts(PERIOD)

    assert set(unmapped["原始科目编码"]) == {"6001", "1001"}
    c001_1001 = unmapped[(unmapped["公司编码"] == "C001") & (unmapped["原始科目编码"] == "1001")]
    c002_1001 = unmapped[(unmapped["公司编码"] == "C002") & (unmapped["原始科目编码"] == "1001")]
    assert len(c001_1001) == 0
    assert len(c002_1001) == 1


def test_global_mapping_counts_toward_coverage():
    _setup_db()
    upsert_standard_account({"标准科目编码": "1001", "标准科目名称": "货币资金", "科目类别": "资产"})
    upsert_account_mapping({"公司编码": "ALL", "原始科目编码": "1001", "标准科目编码": "1001"})

    coverage = get_mapping_coverage(PERIOD)

    assert coverage["total_accounts"] == 3
    assert coverage["mapped_accounts"] == 2
    assert coverage["unmapped_accounts"] == 1
    assert round(coverage["coverage_rate"], 4) == round(2 / 3, 4)
    assert coverage["level"] == "待处理"


def test_suggest_account_mappings_from_existing_history():
    _setup_db()
    upsert_standard_account({"标准科目编码": "1001", "标准科目名称": "货币资金", "科目类别": "资产"})
    upsert_account_mapping({"公司编码": "C001", "原始科目编码": "1001", "标准科目编码": "1001"})

    suggestions = suggest_account_mappings(PERIOD, "C002")

    row = suggestions[suggestions["原始科目编码"] == "1001"].iloc[0]
    assert row["建议标准科目编码"] == "1001"
    assert row["建议原因"] == "其他公司同编码历史映射"
