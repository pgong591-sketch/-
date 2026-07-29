from pathlib import Path

import pandas as pd

from src.import_parser import PlDetailParser, identify_report_type, parse_file
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
    raw = pd.DataFrame([["收入成本费用表"], ["单位:尔遇书馆管理中心"]])

    def fake_resolve_company_code(name):
        return ("10204", "alias") if name == "尔遇书馆管理中心" else (None, "none")

    monkeypatch.setattr("src.import_parser.resolve_company_code", fake_resolve_company_code)

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "10204"


def test_income_cost_company_prefers_header_code_over_filename():
    raw = pd.DataFrame([["收入成本费用表"], ["单位:东莞市茶山新阳光幼儿园 1010702"]])
    source_name = "202503新阳光幼儿园(K051)合并收入成本费用表.xls"

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "1010702"


def test_income_cost_company_does_not_treat_year_as_company_code(monkeypatch):
    raw = pd.DataFrame([["收入成本费用表"], ["单位:尔遇书馆管理中心 2025年03月"]])
    source_name = "202603尔遇书馆管理中心(K0511)收入成本费用明细表.xls"

    def fake_resolve_company_code(name):
        return ("10204", "alias") if name == "尔遇书馆管理中心" else (None, "none")

    monkeypatch.setattr("src.import_parser.resolve_company_code", fake_resolve_company_code)

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "10204"


def test_income_cost_company_does_not_treat_period_as_company_code(monkeypatch):
    raw = pd.DataFrame([["收入成本费用表"], ["单位:东莞市茶山新阳光幼儿园 202503"]])
    source_name = "202503新阳光幼儿园(K051)合并收入成本费用表.xls"

    def fake_resolve_company_code(name):
        return ("1010702", "alias") if name == "东莞市茶山新阳光幼儿园" else (None, "none")

    monkeypatch.setattr("src.import_parser.resolve_company_code", fake_resolve_company_code)

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "1010702"


def test_income_cost_company_explicit_company_code_label_still_wins():
    raw = pd.DataFrame([["收入成本费用表"], ["公司编码:1010702 单位:东莞市茶山新阳光幼儿园"]])
    source_name = "202503新阳光幼儿园(K051)合并收入成本费用表.xls"

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "1010702"


def test_income_cost_company_does_not_scan_item_code_after_unit_line(monkeypatch):
    raw = pd.DataFrame(
        [
            ["收入成本费用表", "", ""],
            ["单位:尔遇书馆管理中心", "", ""],
            ["", "", ""],
            ["科目代码", "科目", "本月发生"],
            ["540128", "劳务费", "5000"],
        ]
    )
    source_name = "202603尔遇书馆管理中心(K0511)收入成本费用明细表.xls"

    def fake_resolve_company_code(name):
        return ("10204", "alias") if name == "尔遇书馆管理中心" else (None, "none")

    monkeypatch.setattr("src.import_parser.resolve_company_code", fake_resolve_company_code)

    company = PlDetailParser()._extract_income_cost_company(raw, None, source_name)

    assert company == "10204"


def test_income_cost_expense_workbook_parses_operating_summary_source_rows():
    df, report_type, info = parse_file(str(SAMPLE), original_filename=SAMPLE.name)

    assert report_type == RT_INCOME_COST_EXPENSE
    assert info["errors"] == []
    assert set(["company_code", "period", "item_code", "item_name", "category", "amount", "ytd_amount"]).issubset(df.columns)
    assert df.iloc[0]["company_code"] == "101010136"
    assert df.iloc[0]["period"] == "202603"
    assert float(df.loc[df["item_name"] == "收入合计", "amount"].iloc[0]) == 60807.82
    assert float(df.loc[df["item_name"] == "成本费用合计", "amount"].iloc[0]) == 80808.13
    assert float(df.loc[df["item_name"] == "净利润", "amount"].iloc[0]) == -20000.31
    assert float(df.loc[df["item_name"] == "收入合计", "ytd_amount"].iloc[0]) != 0

    validation = validate_report_data(df, "pl_detail")
    assert validation.is_valid


def test_income_cost_expense_workbook_writes_structured_ytd_amount(tmp_path):
    path = tmp_path / "202604南城华凯(K051)合并收入成本费用表.xlsx"
    raw = pd.DataFrame(
        [
            ["收入成本费用表", "", "", ""],
            ["单位:华凯校区 101010102", "", "", ""],
            ["", "", "", ""],
            ["科目代码", "科目", "4月", "本年累计"],
            ["6001", "主营业务收入", 100.0, 400.0],
            ["", "收入合计", 100.0, 400.0],
            ["5401", "人工成本", -10.0, -25.0],
            ["5402", "零值费用", 0.0, ""],
            ["5403", "文本费用", "abc", "文本"],
            ["", "成本费用合计", 30.0, 120.0],
            ["", "净利润", 70.0, 280.0],
        ]
    )
    raw.to_excel(path, header=False, index=False)

    df, report_type, info = parse_file(str(path), original_filename=path.name)

    assert report_type == RT_INCOME_COST_EXPENSE
    assert info["errors"] == []
    assert "ytd_amount" in df.columns
    assert float(df.loc[df["item_name"] == "主营业务收入", "amount"].iloc[0]) == 100.0
    assert float(df.loc[df["item_name"] == "主营业务收入", "ytd_amount"].iloc[0]) == 400.0
    assert float(df.loc[df["item_name"] == "收入合计", "amount"].iloc[0]) == 100.0
    assert float(df.loc[df["item_name"] == "收入合计", "ytd_amount"].iloc[0]) == 400.0
    assert float(df.loc[df["item_name"] == "成本费用合计", "ytd_amount"].iloc[0]) == 120.0
    assert float(df.loc[df["item_name"] == "净利润", "ytd_amount"].iloc[0]) == 280.0
    assert float(df.loc[df["item_name"] == "人工成本", "amount"].iloc[0]) == -10.0
    assert float(df.loc[df["item_name"] == "人工成本", "ytd_amount"].iloc[0]) == -25.0
    assert "零值费用" not in set(df["item_name"])
    assert "文本费用" not in set(df["item_name"])

    validation = validate_report_data(df, "pl_detail")
    assert validation.is_valid


def test_income_cost_expense_same_code_different_item_names_get_stable_codes():
    df = pd.DataFrame(
        [
            {
                "company_code": "1010801",
                "period": "202503",
                "item_code": "540128",
                "item_name": "劳务费",
                "category": "费用",
                "amount": 5000.0,
                "dept_code": "",
            },
            {
                "company_code": "1010801",
                "period": "202503",
                "item_code": "540128",
                "item_name": "学生活动费",
                "category": "费用",
                "amount": 1709.12,
                "dept_code": "",
            },
        ]
    )

    stabilized = PlDetailParser()._stabilize_income_cost_item_codes(df)
    validation = validate_report_data(stabilized, "pl_detail")

    assert validation.is_valid
    assert list(stabilized["item_code"]) == ["540128__劳务费", "540128__学生活动费"]


def test_real_202503_income_cost_samples_keep_duplicate_code_item_names_if_available():
    samples = [
        (
            Path("/Users/pokzzz1163.com/Desktop/202503/资料库/收入成本费用表/202503多维学校(K0511)收入成本费用明细表.xls"),
            "1010801",
            {"劳务费", "学生活动费"},
        ),
        (
            Path("/Users/pokzzz1163.com/Desktop/202503/资料库/收入成本费用表/202503新阳光幼儿园(K051)合并收入成本费用表.xls"),
            "1010702",
            {"劳务费", "学生活动费"},
        ),
    ]
    missing = [str(path) for path, _, _ in samples if not path.exists()]
    if missing:
        import pytest

        pytest.skip(f"真实样本不存在: {missing}")

    for path, company_code, expected_names in samples:
        df, report_type, info = parse_file(str(path), original_filename=path.name)
        validation = validate_report_data(df, "pl_detail")
        rows_540128 = df[df["item_code"].astype(str).str.startswith("540128")]

        assert report_type == RT_INCOME_COST_EXPENSE
        assert info["errors"] == []
        assert validation.is_valid
        assert set(df["company_code"]) == {company_code}
        assert expected_names.issubset(set(rows_540128["item_name"]))
        assert rows_540128["item_code"].nunique() >= len(expected_names)
