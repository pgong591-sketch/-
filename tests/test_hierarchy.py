"""Company hierarchy module tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text


def test_company_hierarchy_uses_tree_path(tmp_path, monkeypatch):
    """Build a small hierarchy in an isolated test database."""
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(tmp_path / "finance_dw_test.db"))

    from src.company_hierarchy import rebuild_tree_path, get_company_tree, get_subtree
    from src.db_connection import init_database, get_session

    init_database()

    session = get_session()
    companies = [
        ("GD", "广东事业部", None, 0),
        ("DG001", "东莞XX学校", "GD", 1),
        ("DG002", "东莞YY学校", "GD", 1),
        ("DG001A", "莞城校区", "DG001", 2),
    ]
    for code, name, parent, level in companies:
        session.execute(
            text("""
                INSERT OR IGNORE INTO companies
                    (code, name, parent_code, level)
                VALUES
                    (:code, :name, :parent, :level)
            """),
            {"code": code, "name": name, "parent": parent, "level": level},
        )
    session.commit()
    session.close()

    rebuild_tree_path("GD")

    tree = get_company_tree()
    assert len(tree) == 4
    assert "display_name" in tree.columns

    subtree = get_subtree("DG001", include_self=False)
    assert "DG001A" in subtree["code"].tolist()
    assert "GD" not in subtree["code"].tolist()

    subtree_with_self = get_subtree("DG001", include_self=True)
    assert "DG001" in subtree_with_self["code"].tolist()


def test_import_companies_from_excel_builds_root_and_aliases(tmp_path, monkeypatch):
    """Importing the organization source file should also seed aliases."""
    monkeypatch.setenv("FINANCE_DW_DB_PATH", str(tmp_path / "finance_dw_test.db"))

    import pandas as pd

    from src.company_aliases import resolve_company_code
    from src.company_hierarchy import get_company_tree, import_companies_from_excel
    from src.db_connection import init_database

    init_database()

    source = pd.DataFrame({
        "\u516c\u53f8\u7f16\u7801": ["101", "10101", "1010101"],
        "\u516c\u53f8\u540d\u79f0": ["GroupCo", "DivisionCo", "CampusCo"],
        "\u4e0a\u7ea7\u516c\u53f8": ["TopGroup", "GroupCo", "DivisionCo"],
        "\u7b80\u79f0": ["Mgmt", "Division", "Campus"],
    })
    source_path = tmp_path / "companies.xlsx"
    source.to_excel(source_path, index=False)

    result = import_companies_from_excel(str(source_path))

    assert result["success"], result["errors"]
    assert result["total"] == 3

    tree = get_company_tree()
    root = tree[tree["code"] == "ROOT"].iloc[0]
    group = tree[tree["code"] == "101"].iloc[0]
    campus = tree[tree["code"] == "1010101"].iloc[0]

    assert root["name"] == "TopGroup"
    assert group["parent_code"] == "ROOT"
    assert group["tree_path"] == "/ROOT/101"
    assert campus["level"] == 3
    assert campus["tree_path"] == "/ROOT/101/10101/1010101"
    assert resolve_company_code("Mgmt")[0] == "101"
    assert resolve_company_code("Campus")[0] == "1010101"
