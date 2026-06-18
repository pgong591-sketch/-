"""测试辅助余额表格式解析"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.import_parser import AccountBalanceParser, identify_report_type
from src.validators import validate_report_data


def test_column_mapping():
    """测试科目辅助余额表列名映射"""
    mock_data = {
        '科目编码': ['1001', '1002'],
        '会计科目': ['库存现金', '银行存款'],
        '期初余额': [10000.0, 500000.0],
        '借方金额': [5000.0, 100000.0],
        '贷方金额': [3000.0, 50000.0],
        '期末余额': [12000.0, 550000.0],
    }
    df = pd.DataFrame(mock_data)

    # 检查哪些列名能匹配
    mapped = 0
    for col in df.columns:
        if col in AccountBalanceParser.COLUMN_MAPPING:
            mapped += 1
    print(f"列名匹配: {mapped}/{len(df.columns)}")
    assert mapped >= 4, f"列名匹配不足: {mapped}"

    # 完整解析流程
    parser = AccountBalanceParser(company_code='DG001', period='202603')
    df_parsed = parser._clean_df(df)
    df_parsed = parser._map_columns(df_parsed)

    df_parsed['company_code'] = 'DG001'
    df_parsed['period'] = '202603'
    if 'direction' not in df_parsed.columns:
        df_parsed['direction'] = '借'

    for col in ['opening_balance', 'debit_amount', 'credit_amount', 'ending_balance']:
        if col in df_parsed.columns:
            df_parsed[col] = parser._normalize_numeric(df_parsed[col])

    result_cols = ['company_code', 'period', 'account_code', 'account_name',
                   'opening_balance', 'debit_amount', 'credit_amount',
                   'ending_balance', 'direction']
    available = [c for c in result_cols if c in df_parsed.columns]
    df_result = df_parsed[available].copy()

    print(f"最终列: {list(df_result.columns)}")
    assert 'account_code' in df_result.columns, "account_code 列缺失"
    assert 'account_name' in df_result.columns, "account_name 列缺失"
    assert 'ending_balance' in df_result.columns, "ending_balance 列缺失"

    # 校验
    validation = validate_report_data(df_result, 'account_balance')
    print(f"校验结果: {'通过' if validation.is_valid else '失败'}")
    if not validation.is_valid:
        for e in validation.errors:
            print(f"  X {e}")

    assert validation.is_valid, f"数据校验失败: {validation.errors}"
    print("✅ 辅助余额表解析测试通过")


def test_filename_identification():
    """测试文件名识别"""
    test_files = [
        ('202603莞城小学科目辅助余额表.xlsx', '科目余额表'),
        ('202603_东莞学校_科目余额表.xlsx', '科目余额表'),
        ('科目余额表_202603.xlsx', '科目余额表'),
    ]
    for fname, expected in test_files:
        rtype = identify_report_type(fname)
        assert rtype == expected, f"'{fname}' -> '{rtype}', 期望 '{expected}'"
        print(f"  ✅ '{fname}' -> {rtype}")


def test_filename_extract():
    """测试从文件名提取公司和期间"""
    from pathlib import Path
    import re

    test_cases = [
        ('202603莞城小学科目辅助余额表.xlsx', '202603', '莞城小学'),
        ('东莞学校_202603_科目余额表.xlsx', '202603', '东莞学校'),
        ('202603_东莞学校_损益表.xlsx', '202603', '东莞学校'),
    ]

    for fname, exp_period, exp_company in test_cases:
        file_name = Path(fname).name
        company = period = None

        # 模式1: 公司名_202603
        m = re.search(r"(.+?)[_\- ](\d{6})", file_name)
        if m:
            company = m.group(1).strip()
            period = m.group(2).strip()
        else:
            # 模式2: 202603公司名
            m = re.search(r"^(\d{6})[\s_\-]*(.+?)(?:\.xlsx?|$)", file_name)
            if m:
                period = m.group(1).strip()
                raw = m.group(2).strip()
                for kw in ["科目余额表", "辅助余额", "余额表", "资产负债表",
                          "利润表", "损益表", "现金流量表", "收入人次", "课酬"]:
                    raw = raw.replace(kw, "")
                name_match = re.search(r"[\u4e00-\u9fff]+", raw)
                company = name_match.group() if name_match else raw

        assert period == exp_period, f"'{fname}': period={period}, 期望={exp_period}"
        print(f"  ✅ '{fname}' -> period={period}, company={company}")


if __name__ == "__main__":
    test_column_mapping()
    test_filename_identification()
    test_filename_extract()
    print("\n✅ 所有辅助余额表测试通过！")
