"""Regression tests for filtering footer rows from account-balance imports."""
from pathlib import Path


def test_filter_footer_rows_from_sample_workbook():
    import pytest

    pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")

    sample = Path("data/202603莞城小学科目辅助余额表.xlsx")
    if not sample.exists():
        pytest.skip(f"sample workbook not available: {sample}")

    from src.import_parser import AccountBalanceParser

    parser = AccountBalanceParser(company_code="莞城小学", period="202603")
    df = parser.parse(str(sample))

    all_text = " ".join(df["account_name"].astype(str) + df["account_code"].astype(str))
    assert "制表人" not in all_text
    assert "核算单位" not in all_text
