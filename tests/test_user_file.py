"""Sample-workbook parser smoke tests."""
from pathlib import Path


def test_sample_account_balance_workbook_parses_and_validates():
    import pytest

    pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")

    sample = Path("data/202603莞城小学科目辅助余额表.xlsx")
    if not sample.exists():
        pytest.skip(f"sample workbook not available: {sample}")

    from src.import_parser import AccountBalanceParser, parse_and_validate
    from src.report_types import RT_ACCOUNT_BALANCE, get_table_name

    parser = AccountBalanceParser()
    df = parser.parse(str(sample))

    assert len(df) > 0
    assert "account_name" in df.columns
    assert "account_code" in df.columns
    assert df["account_name"].notna().any()
    assert df["account_code"].notna().any()

    _, rtype, validation, _ = parse_and_validate(str(sample))
    assert rtype == RT_ACCOUNT_BALANCE
    assert get_table_name(rtype) == "account_balance"
    assert validation.is_valid, validation.errors[:10]
