import json

import pytest
from sqlalchemy import text

from src.db_connection import get_session, init_database
from src.shared_name_mapping import (
    CONFIRMED_SHARED_COMPANY_ALIASES,
    SHARED_NAME_MAPPING_SCHEMA_VERSION,
    build_shared_name_mapping_snapshot,
    ensure_confirmed_shared_company_aliases,
    publish_shared_name_mapping_snapshot,
)


def _seed_companies(*, duplicate_short_name: bool = False):
    init_database()
    session = get_session()
    try:
        session.execute(text("DELETE FROM company_aliases"))
        session.execute(text("DELETE FROM companies"))
        rows = [
            ("101", "广东多维教育科技集团有限公司", "管理中心", 1),
            ("101010102", "华凯校区", "华凯校区", 1),
            ("101010103", "石龙校区", "石龙校区", 1),
            ("101010130", "寮步石大校区", "寮步石大校区", 1),
            ("101010131", "茶山学前校区", "茶山学前", 1),
            ("101010133", "南城虎翼营", "南城虎翼营", 1),
            ("10204", "深圳尔遇文化发展有限公司", "尔遇书馆管理中心", 1),
            ("999", "停用公司", "停用简称", 0),
        ]
        if duplicate_short_name:
            rows.append(("998", "冲突公司", "管理中心", 1))
        for code, name, short_name, status in rows:
            session.execute(
                text(
                    """
                    INSERT INTO companies
                        (code, name, short_name, level, tree_path, is_leaf, is_consolidated, status)
                    VALUES
                        (:code, :name, :short_name, 1, :tree_path, 1, 1, :status)
                    """
                ),
                {"code": code, "name": name, "short_name": short_name, "tree_path": f"/{code}", "status": status},
            )
        session.execute(
            text(
                """
                INSERT INTO company_aliases (alias, company_code, source, status)
                VALUES
                    ('广东多维教育', '101', 'manual', 1),
                    ('南城', '101010133', 'manual', 1),
                    ('茶山校区', '101010131', 'budget', 1),
                    ('旧停用简称', '999', 'manual', 1)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def test_shared_name_mapping_snapshot_contains_master_aliases_and_campus_names():
    _seed_companies()
    ensure_confirmed_shared_company_aliases()

    snapshot = build_shared_name_mapping_snapshot()
    records = snapshot["records"]
    aliases = {(row["alias"], row["company_code"], row["alias_type"], row["enabled"]) for row in records}
    alias_targets = {
        row["alias"]: row["company_code"]
        for row in records
        if row.get("enabled") and row["alias"] in {alias for alias, _ in CONFIRMED_SHARED_COMPANY_ALIASES} | {"南城"}
    }

    assert snapshot["schema_version"] == SHARED_NAME_MAPPING_SCHEMA_VERSION
    assert snapshot["source_system"] == "finance_dw"
    assert snapshot["stats"]["company_count"] == 8
    assert ("101", "101", "company_code", True) in aliases
    assert ("广东多维教育科技集团有限公司", "101", "canonical_name", True) in aliases
    assert ("广东多维教育", "101", "historical_alias", True) in aliases
    assert ("南城", "101010133", "historical_alias", True) in aliases
    assert alias_targets["南城校区"] == "101010102"
    assert alias_targets["南城虎翼营"] == "101010133"
    assert alias_targets["寮步校区"] == "101010130"
    assert ("茶山校区", "101010131", "historical_alias", True) in aliases
    assert ("茶山校区", "101010131", "campus_name", True) in aliases
    assert ("旧停用简称", "999", "historical_alias", False) in aliases
    assert snapshot["conflicts"] == []


def test_confirmed_shared_company_aliases_are_idempotent_and_do_not_remap_nancheng(monkeypatch):
    _seed_companies()
    monkeypatch.setattr(
        "src.shared_name_mapping.get_budget_campus_name_mappings",
        lambda: {
            "华凯校区": ("华凯校区", "南城华凯校区", "南城校区"),
            "南城虎翼营": ("南城虎翼营", "南城虎翼"),
            "寮步校区": ("寮步石大校区",),
            "茶山校区": ("茶山学前校区",),
        },
    )

    first = ensure_confirmed_shared_company_aliases()
    second = ensure_confirmed_shared_company_aliases()
    snapshot = build_shared_name_mapping_snapshot()
    alias_targets = {
        row["alias"]: row["company_code"]
        for row in snapshot["records"]
        if row.get("enabled") and row["alias"] in {alias for alias, _ in CONFIRMED_SHARED_COMPANY_ALIASES} | {"南城"}
    }

    assert first["conflicts"] == []
    assert first["inserted"] == 8
    assert second["conflicts"] == []
    assert second["inserted"] == 0
    assert second["unchanged"] == len(CONFIRMED_SHARED_COMPANY_ALIASES)
    assert alias_targets["华凯校区"] == "101010102"
    assert alias_targets["南城华凯校区"] == "101010102"
    assert alias_targets["南城校区"] == "101010102"
    assert alias_targets["南城虎翼营"] == "101010133"
    assert alias_targets["南城虎翼"] == "101010133"
    assert alias_targets["寮步校区"] == "101010130"
    assert alias_targets["寮步石大校区"] == "101010130"
    assert alias_targets["茶山校区"] == "101010131"
    assert alias_targets["茶山学前校区"] == "101010131"
    assert alias_targets["南城"] == "101010133"
    assert snapshot["stats"]["conflict_count"] == 0
    assert snapshot["stats"]["unmatched_alias_count"] == 0


def test_publish_shared_name_mapping_snapshot_writes_atomically(tmp_path):
    _seed_companies()
    target = tmp_path / "mapping.json"

    result = publish_shared_name_mapping_snapshot(target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["path"] == str(target)
    assert result["record_count"] == len(payload["records"])
    assert payload["schema_version"] == SHARED_NAME_MAPPING_SCHEMA_VERSION
    assert not list(tmp_path.glob("*.tmp"))


def test_publish_shared_name_mapping_blocks_duplicate_enabled_alias(tmp_path):
    _seed_companies(duplicate_short_name=True)

    snapshot = build_shared_name_mapping_snapshot()

    assert any(item["alias"] == "管理中心" for item in snapshot["conflicts"])
    with pytest.raises(ValueError):
        publish_shared_name_mapping_snapshot(tmp_path / "mapping.json")
