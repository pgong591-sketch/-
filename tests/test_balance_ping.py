"""Trial-balance validation cases for the neutral direction value."""


def test_account_balance_ping_direction_cases():
    import pytest

    pd = pytest.importorskip("pandas")

    from src.validators import validate_account_balance

    test_cases = [
        (0.0, 0.0, 5600.0, 5600.0, "平", True),
        (0.0, 0.0, 415.43, 415.43, "平", True),
        (0.0, 38000.0, 84000.0, 46000.0, "平", True),
        (0.0, 5600.0, 0.0, 5600.0, "平", True),
        (0.0, 46000.0, 2179.4, 43820.6, "平", True),
        (11643.05, 84689.97, 56095.98, 16950.94, "贷", True),
        (10000.0, 5000.0, 3000.0, 12000.0, "借", True),
        (0.0, 100.0, 200.0, 300.0, "平", False),
    ]

    for idx, (opening, debit, credit, ending, direction, expected) in enumerate(test_cases):
        df = pd.DataFrame([{
            "company_code": "T",
            "period": "202603",
            "account_code": f"A{idx:03d}",
            "account_name": f"测试{idx}",
            "opening_balance": opening,
            "debit_amount": debit,
            "credit_amount": credit,
            "ending_balance": ending,
            "direction": direction,
        }])
        result = validate_account_balance(df)
        assert result.is_valid is expected, result.errors
