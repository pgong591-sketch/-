"""校验器单元测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from src.validators import validate_account_balance, validate_report_data


def test_account_balance_valid():
    """测试科目余额表校验 - 正常数据"""
    df = pd.DataFrame({
        "company_code": ["DG001"],
        "period": ["202603"],
        "account_code": ["1001"],
        "account_name": ["现金"],
        "opening_balance": [1000.0],
        "debit_amount": [500.0],
        "credit_amount": [200.0],
        "ending_balance": [1300.0],
    })
    result = validate_account_balance(df)
    assert result.is_valid, f"期望通过，但失败: {result.errors}"


def test_account_balance_imbalance():
    """测试科目余额表校验 - 试算不平衡"""
    df = pd.DataFrame({
        "company_code": ["DG001"],
        "period": ["202603"],
        "account_code": ["1001"],
        "account_name": ["现金"],
        "opening_balance": [1000.0],
        "debit_amount": [500.0],
        "credit_amount": [200.0],
        "ending_balance": [1000.0],  # 应该是1300
    })
    result = validate_account_balance(df)
    assert not result.is_valid, "期望试算不平衡错误"


def test_validate_report_data():
    """测试综合校验"""
    df = pd.DataFrame({
        "company_code": ["DG001"],
        "period": ["202603"],
        "account_code": ["1001"],
        "account_name": ["现金"],
        "opening_balance": [1000.0],
        "debit_amount": [500.0],
        "credit_amount": [200.0],
        "ending_balance": [1300.0],
    })
    result = validate_report_data(df, "account_balance")
    assert result.is_valid


if __name__ == "__main__":
    test_account_balance_valid()
    test_account_balance_imbalance()
    test_validate_report_data()
    print("所有测试通过！")
