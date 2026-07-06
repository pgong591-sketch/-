from pathlib import Path

import pandas as pd

from src.import_parser import identify_report_type, parse_file
from src.report_types import (
    RT_BALANCE_SHEET,
    RT_MGMT_DEPT_INCOME_COST,
    RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST,
    RT_NON_SUBJECT_TEACHING_FEE,
    RT_REVENUE_VOLUME,
)


def test_identify_matrix_and_teaching_fee_by_preview():
    mgmt_preview = pd.DataFrame(
        [
            ["会计科目", "统计方式", "余额方向", "【部门档案：董事会】", "【部门档案：品牌部】"],
            ["主营业务收入", "借方", "", 100, 0],
        ]
    )
    assert identify_report_type("tmp.xlsx", mgmt_preview) == RT_MGMT_DEPT_INCOME_COST

    non_subject_preview = pd.DataFrame(
        [
            ["会计科目", "统计方式", "余额方向", "【部门档案：素质管理中心】", "【部门档案：学术中心】"],
            ["主营业务收入", "借方", "", 100, 200],
        ]
    )
    assert identify_report_type("tmp.xlsx", non_subject_preview) == RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST

    teaching_preview = pd.DataFrame(
        [
            ["年份", "月份", "职员代码", "职员姓名", "打印部门名称", "总收入"],
            [2026, 3, "E0001", "测试", "素质中心教研部", 1000],
        ]
    )
    assert identify_report_type("tmp.xlsx", teaching_preview) == RT_NON_SUBJECT_TEACHING_FEE


def test_identify_revenue_volume_by_original_filename():
    original_name = "202603收入人次表.xls"
    assert identify_report_type("tmp.xls", None, source_name=original_name) == RT_REVENUE_VOLUME


def test_non_subject_management_center_balance_sheet_identifies_as_balance_sheet():
    names = [
        "非学科管理中心资产负债表.xlsx",
        "非学科管理中心合并资产负债表.xlsx",
        "202603非学科管理中心(K合01表)合并资产负债表.xlsx",
    ]

    for name in names:
        assert identify_report_type("tmp.xlsx", None, source_name=name) == RT_BALANCE_SHEET


def test_non_subject_management_center_income_cost_still_identifies_as_dept_report():
    names = [
        "202603非学科管理中心部门收入成本费用表.xlsx",
        "202603非学科管理中心收入成本费用表.xlsx",
        "202603非学科管理中心管理公司收入成本费用表.xlsx",
    ]

    for name in names:
        assert identify_report_type("tmp.xlsx", None, source_name=name) == RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST


def test_management_center_balance_sheet_does_not_identify_as_dept_income_cost():
    assert identify_report_type("tmp.xlsx", None, source_name="202603管理中心资产负债表.xlsx") == RT_BALANCE_SHEET


def test_non_subject_management_center_company_name_does_not_override_common_report_types():
    cases = [
        ("202603非学科管理中心利润表.xlsx", "损益表"),
        ("202603非学科管理中心损益表.xlsx", "损益表"),
        ("202603非学科管理中心科目余额表.xlsx", "科目余额表"),
        ("202603非学科管理中心现金流量表.xlsx", "现金流量表"),
    ]

    for name, expected in cases:
        assert identify_report_type("tmp.xlsx", None, source_name=name) == expected


def test_parse_real_matrix_workbooks_if_available():
    base = Path("data/incoming")
    mgmt_fp = base / "202603_mgmt_dept_income_cost.xlsx"
    non_subject_fp = base / "202603_non_subject_mgmt_dept_income_cost.xlsx"
    fee_fp = base / "202603_non_subject_teaching_fee.xlsx"
    revenue_fp = base / "202603_revenue_volume.xls"

    if mgmt_fp.exists():
        df, rtype, info = parse_file(str(mgmt_fp), original_filename="202603管理中心部门收入成本费用表.xlsx")
        assert df is not None, info
        assert rtype == RT_MGMT_DEPT_INCOME_COST
        assert {"company_code", "period", "dept_code", "income_amount", "expense_amount"}.issubset(df.columns)
        assert len(df) > 0

    if non_subject_fp.exists():
        df, rtype, info = parse_file(str(non_subject_fp), original_filename="202603非学科管理中心部门收入成本费用表.xlsx")
        assert df is not None, info
        assert rtype == RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST
        assert {"company_code", "period", "dept_code", "subject_type", "income_amount"}.issubset(df.columns)
        assert len(df) > 0

    if fee_fp.exists():
        df, rtype, info = parse_file(str(fee_fp), original_filename="202603非学科课酬.xlsx")
        assert df is not None, info
        assert rtype == RT_NON_SUBJECT_TEACHING_FEE
        assert {"company_code", "period", "teacher_id", "course_type", "total_amount"}.issubset(df.columns)
        assert len(df) > 0

    if revenue_fp.exists():
        df, rtype, info = parse_file(str(revenue_fp), original_filename="202603收入人次表.xls")
        assert df is not None, info
        assert rtype == RT_REVENUE_VOLUME
        assert {
            "company_code",
            "period",
            "product_line",
            "data_period",
            "business_period",
            "calendar_quarter",
            "source_quarter_label",
            "campus_name",
            "grade",
            "subject",
            "customer_count",
            "revenue_amount",
        }.issubset(df.columns)
        assert len(df) > 0
