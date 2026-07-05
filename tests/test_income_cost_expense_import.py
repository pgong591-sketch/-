from pathlib import Path

import pandas as pd

from src.import_parser import identify_report_type, parse_file
from src.report_types import RT_INCOME_COST_EXPENSE
from src.validators import validate_report_data


SAMPLE = Path("data/incoming/202603_K051_income_cost_expense.xls")


def test_income_cost_expense_workbook_identifies_as_pl_detail():
    preview = pd.read_excel(SAMPLE, nrows=12, header=None)

    assert identify_report_type(str(SAMPLE), preview, source_name=SAMPLE.name) == RT_INCOME_COST_EXPENSE


def test_yu_bookstore_management_center_income_cost_identifies_as_pl_detail():
    preview = pd.read_excel(SAMPLE, nrows=12, header=None)
    source_name = "202603尔遇书馆管理中心(K0511)收入成本费用明细表.xls"

    assert identify_report_type("tmp.xls", preview, source_name=source_name) == RT_INCOME_COST_EXPENSE


def test_yu_bookstore_management_center_maps_to_10204(monkeypatch):
    source_name = "202603尔遇书馆管理中心(K0511)收入成本费用明细表.xls"

    def fake_resolve_company_code(name):
        return ("10204", "alias") if name == "尔遇书馆管理中心" else (None, "none")

    monkeypatch.setattr("src.import_parser.resolve_company_code", fake_resolve_company_code)

    df, report_type, info = parse_file(str(SAMPLE), original_filename=source_name)

    assert report_type == RT_INCOME_COST_EXPENSE
    assert info["errors"] == []
    assert set(df["company_code"]) == {"10204"}


def test_income_cost_expense_workbook_parses_operating_summary_source_rows():
    df, report_type, info = parse_file(str(SAMPLE), original_filename=SAMPLE.name)

    assert report_type == RT_INCOME_COST_EXPENSE
    assert info["errors"] == []
    assert set(["company_code", "period", "item_code", "item_name", "category", "amount"]).issubset(df.columns)
    assert df.iloc[0]["company_code"] == "101010136"
    assert df.iloc[0]["period"] == "202603"
    assert float(df.loc[df["item_name"] == "收入合计", "amount"].iloc[0]) == 60807.82
    assert float(df.loc[df["item_name"] == "成本费用合计", "amount"].iloc[0]) == 80808.13
    assert float(df.loc[df["item_name"] == "净利润", "amount"].iloc[0]) == -20000.31

    validation = validate_report_data(df, "pl_detail")
    assert validation.is_valid
