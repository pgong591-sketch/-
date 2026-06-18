"""Import-protection regression checks."""
from pathlib import Path


def test_duplicate_check_failure_blocks_import():
    source = Path("src/reports.py").read_text(encoding="utf-8")

    assert "pass  # 重复检查失败不应阻止导入" not in source
    assert "重复导入检查失败，已阻止写库" in source
    assert "finally:\n            s.close()" in source
