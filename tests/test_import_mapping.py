"""Import-query safety checks."""
from pathlib import Path


def test_reports_uses_bound_in_clauses():
    source = Path("src/reports.py").read_text(encoding="utf-8")

    assert "def _quote_list" not in source
    assert "def _bind_in_clause" in source
    assert "_bind_in_clause(\"ab.company_code\"" in source
    assert "_bind_in_clause(\"ab.period\"" in source
    assert "_bind_in_clause(\"ab.account_code\"" in source
