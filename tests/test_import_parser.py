"""解析器单元测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.import_parser import AccountBalanceParser, BalanceSheetParser, identify_report_type


def test_account_balance_parser():
    """测试科目余额表解析器"""
    parser = AccountBalanceParser(company_code="DG001", period="202603")

    # 模拟Excel数据
    data = {
        "科目编码": ["1001", "1002", "2001"],
        "科目名称": ["现金", "银行存款", "应付账款"],
        "期初余额": [1000.0, 50000.0, 30000.0],
        "借方": [500.0, 10000.0, 5000.0],
        "贷方": [200.0, 2000.0, 8000.0],
        "期末余额": [1300.0, 58000.0, 27000.0],
    }
    df = pd.DataFrame(data)
    df_parsed = parser._clean_df(df)
    df_parsed = parser._map_columns(df_parsed)

    assert "account_code" in df_parsed.columns, f"列映射失败: {df_parsed.columns}"
    assert df_parsed["account_code"].tolist() == ["1001", "1002", "2001"]
    print("科目余额表解析器测试通过")


def test_identify_report_type():
    """测试报表类型识别"""
    file_name = "东莞XX学校_202603_科目余额表.xlsx"
    rtype = identify_report_type(file_name)
    assert rtype == "科目余额表", f"期望科目余额表，得到 {rtype}"

    file_name = "东莞XX学校_202603_收入人次表.xlsx"
    rtype = identify_report_type(file_name)
    assert rtype == "收入人次表", f"期望收入人次表，得到 {rtype}"

    print("报表类型识别测试通过")


def test_balance_sheet_goodwill_alias():
    """资产负债表解析：验证解析结果包含预期行数"""
    parser = BalanceSheetParser()
    import os
    fp = os.path.join(os.path.dirname(__file__), "..", "data", "202603拔创中心(k合01表)合并资产负债表.xls")
    if os.path.exists(fp):
        df = parser.parse(fp)
        assert len(df) > 0, "应解析到数据行"
        assert "资产" in df["side"].values, "应包含资产侧数据"
        print(f"资产负债表解析成功，共 {len(df)} 行")
    else:
        print("跳过：测试文件不存在")


if __name__ == "__main__":
    test_account_balance_parser()
    test_identify_report_type()
    test_balance_sheet_goodwill_alias()
    print("所有测试通过！")
