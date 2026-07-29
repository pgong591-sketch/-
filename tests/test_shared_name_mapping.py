import json

import pytest
from sqlalchemy import text

from src.db_connection import get_session, init_database
from src.shared_name_mapping import (
    SHARED_NAME_MAPPING_SCHEMA_VERSION,
    build_shared_name_mapping_snapshot,
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
            ("101010103", "石龙校区", "石龙校区", 1),
            ("101010131", "茶山学前校区", "茶山学前", 1),
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

    snapshot = build_shared_name_mapping_snapshot()
    records = snapshot["records"]
    aliases = {(row["alias"], row["company_code"], row["alias_type"], row["enabled"]) for row in records}

    assert snapshot["schema_version"] == SHARED_NAME_MAPPING_SCHEMA_VERSION
    assert snapshot["source_system"] == "finance_dw"
    assert snapshot["stats"]["company_count"] == 5
    assert ("101", "101", "company_code", True) in aliases
    assert ("广东多维教育科技集团有限公司", "101", "canonical_name", True) in aliases
    assert ("广东多维教育", "101", "historical_alias", True) in aliases
    assert ("茶山校区", "101010131", "historical_alias", True) in aliases
    assert ("茶山校区", "101010131", "campus_name", True) in aliases
    assert ("旧停用简称", "999", "historical_alias", False) in aliases
    assert snapshot["conflicts"] == []


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
