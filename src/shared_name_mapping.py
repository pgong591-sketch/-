"""Shared company-name mapping snapshot for downstream systems.

The finance warehouse remains the source of truth.  Downstream systems consume
the exported JSON file read-only instead of reading this SQLite database
directly.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .base_settings_service import get_budget_campus_name_mappings
from .company_aliases import ensure_company_alias_table
from .db_connection import PROJECT_ROOT, execute_sql, get_session


SHARED_NAME_MAPPING_SCHEMA_VERSION = "finance_dw.shared_name_mapping.v1"
SHARED_NAME_MAPPING_SOURCE_SYSTEM = "finance_dw"
SHARED_NAME_MAPPING_ENV = "FINANCE_SHARED_NAME_MAPPING_PATH"
CONFIRMED_SHARED_COMPANY_ALIASES: tuple[tuple[str, str], ...] = (
    ("华凯校区", "101010102"),
    ("南城华凯校区", "101010102"),
    ("南城校区", "101010102"),
    ("南城虎翼营", "101010133"),
    ("南城虎翼", "101010133"),
    ("寮步校区", "101010130"),
    ("寮步石大校区", "101010130"),
    ("茶山校区", "101010131"),
    ("茶山学前校区", "101010131"),
)


def ensure_confirmed_shared_company_aliases(
    *,
    source: str = "shared_mapping_user_confirmed_20260729",
) -> dict[str, Any]:
    """Idempotently persist user-confirmed shared aliases into company_aliases."""
    ensure_company_alias_table()
    session = get_session()
    inserted = 0
    reactivated = 0
    unchanged = 0
    conflicts: list[dict[str, str]] = []
    try:
        for alias, company_code in CONFIRMED_SHARED_COMPANY_ALIASES:
            existing = session.execute(
                text(
                    """
                    SELECT company_code, COALESCE(status, 1) AS status
                    FROM company_aliases
                    WHERE alias = :alias
                    """
                ),
                {"alias": alias},
            ).fetchone()
            if existing and str(existing[0]).strip() != company_code:
                conflicts.append(
                    {
                        "alias": alias,
                        "existing_company_code": str(existing[0]).strip(),
                        "confirmed_company_code": company_code,
                    }
                )
                continue
            if existing:
                if int(existing[1] or 0) != 1:
                    session.execute(
                        text(
                            """
                            UPDATE company_aliases
                            SET status = 1,
                                source = :source,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE alias = :alias
                            """
                        ),
                        {"alias": alias, "source": source},
                    )
                    reactivated += 1
                else:
                    unchanged += 1
                continue
            session.execute(
                text(
                    """
                    INSERT INTO company_aliases (alias, company_code, source, status)
                    VALUES (:alias, :company_code, :source, 1)
                    """
                ),
                {"alias": alias, "company_code": company_code, "source": source},
            )
            inserted += 1
        if conflicts:
            session.rollback()
            return {"inserted": 0, "reactivated": 0, "unchanged": unchanged, "conflicts": conflicts}
        session.commit()
        return {"inserted": inserted, "reactivated": reactivated, "unchanged": unchanged, "conflicts": []}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_alias(value: Any) -> str:
    return "".join(_clean(value).split())


def get_shared_name_mapping_path() -> Path:
    configured = os.environ.get(SHARED_NAME_MAPPING_ENV)
    if configured:
        return Path(configured).expanduser()
    return PROJECT_ROOT / "data" / "shared_name_mapping.json"


def _company_rows() -> list[dict[str, Any]]:
    df = execute_sql(
        """
        SELECT
            CAST(code AS TEXT) AS company_code,
            COALESCE(name, '') AS canonical_name,
            COALESCE(short_name, '') AS short_name,
            COALESCE(status, 1) AS status
        FROM companies
        ORDER BY code
        """
    )
    return df.to_dict("records") if not df.empty else []


def _company_alias_rows() -> list[dict[str, Any]]:
    try:
        df = execute_sql(
            """
            SELECT
                CAST(a.company_code AS TEXT) AS company_code,
                COALESCE(c.name, '') AS canonical_name,
                COALESCE(c.short_name, '') AS short_name,
                COALESCE(c.status, 1) AS company_status,
                a.alias AS alias,
                COALESCE(a.source, '') AS source,
                COALESCE(a.status, 1) AS alias_status
            FROM company_aliases a
            LEFT JOIN companies c ON c.code = a.company_code
            ORDER BY a.alias, a.company_code
            """
        )
        return df.to_dict("records") if not df.empty else []
    except Exception:
        return []


def _record(
    *,
    company_code: str,
    canonical_name: str,
    short_name: str,
    alias: str,
    alias_type: str,
    enabled: bool,
    status: str | None = None,
    source: str = "",
) -> dict[str, Any] | None:
    code = _clean(company_code)
    name = _clean(canonical_name) or code
    alias_value = _clean(alias)
    if not code or not alias_value:
        return None
    enabled_bool = bool(enabled)
    return {
        "source_system": SHARED_NAME_MAPPING_SOURCE_SYSTEM,
        "company_code": code,
        "canonical_name": name,
        "short_name": _clean(short_name),
        "alias": alias_value,
        "alias_type": alias_type,
        "enabled": enabled_bool,
        "status": status or ("enabled" if enabled_bool else "disabled"),
        "source": _clean(source),
    }


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in records:
        key = (_normalize_alias(item.get("alias")), item.get("company_code", ""), item.get("alias_type", ""))
        deduped.setdefault(key, item)
    return sorted(
        deduped.values(),
        key=lambda item: (
            _normalize_alias(item.get("alias")),
            _clean(item.get("company_code")),
            _clean(item.get("alias_type")),
        ),
    )


def _detect_conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alias_targets: dict[str, dict[str, Any]] = {}
    for item in records:
        if not item.get("enabled", True):
            continue
        alias_key = _normalize_alias(item.get("alias"))
        if not alias_key:
            continue
        bucket = alias_targets.setdefault(alias_key, {"alias": _clean(item.get("alias")), "company_codes": set()})
        bucket["company_codes"].add(_clean(item.get("company_code")))

    conflicts = []
    for item in alias_targets.values():
        codes = sorted(code for code in item["company_codes"] if code)
        if len(codes) > 1:
            conflicts.append({"alias": item["alias"], "company_codes": codes})
    return sorted(conflicts, key=lambda item: item["alias"])


def build_shared_name_mapping_snapshot() -> dict[str, Any]:
    companies = _company_rows()
    code_lookup: dict[str, dict[str, Any]] = {
        _clean(row.get("company_code")): row for row in companies if _clean(row.get("company_code"))
    }
    exact_lookup: dict[str, set[str]] = {}
    records: list[dict[str, Any]] = []
    unmatched_aliases: list[dict[str, str]] = []

    def add_record(**kwargs) -> None:
        item = _record(**kwargs)
        if item:
            records.append(item)
            if item.get("enabled", True):
                exact_lookup.setdefault(_normalize_alias(item["alias"]), set()).add(item["company_code"])

    for row in companies:
        code = _clean(row.get("company_code"))
        name = _clean(row.get("canonical_name")) or code
        short_name = _clean(row.get("short_name"))
        enabled = int(row.get("status") or 0) == 1
        add_record(company_code=code, canonical_name=name, short_name=short_name, alias=code, alias_type="company_code", enabled=enabled)
        add_record(company_code=code, canonical_name=name, short_name=short_name, alias=name, alias_type="canonical_name", enabled=enabled)
        if short_name and short_name != name:
            add_record(company_code=code, canonical_name=name, short_name=short_name, alias=short_name, alias_type="short_name", enabled=enabled)

    for row in _company_alias_rows():
        code = _clean(row.get("company_code"))
        company = code_lookup.get(code, {})
        enabled = int(row.get("alias_status") or 0) == 1 and int(row.get("company_status") or 0) == 1
        add_record(
            company_code=code,
            canonical_name=_clean(row.get("canonical_name")) or _clean(company.get("canonical_name")) or code,
            short_name=_clean(row.get("short_name")) or _clean(company.get("short_name")),
            alias=_clean(row.get("alias")),
            alias_type="historical_alias",
            enabled=enabled,
            source=_clean(row.get("source")),
        )

    for budget_name, actual_names in get_budget_campus_name_mappings().items():
        budget_alias_key = _normalize_alias(budget_name)
        target_codes: set[str] = set()
        for actual_name in actual_names:
            target_codes.update(exact_lookup.get(_normalize_alias(actual_name), set()))
        if len(target_codes) == 1:
            code = next(iter(target_codes))
            existing_codes = exact_lookup.get(budget_alias_key, set())
            if existing_codes and existing_codes != {code}:
                unmatched_aliases.append(
                    {
                        "alias": _clean(budget_name),
                        "alias_type": "campus_name",
                        "reason": "校区名已作为其它公司正式名称/别名存在，未发布为共享别名",
                        "candidate_company_codes": ",".join(sorted(target_codes | existing_codes)),
                    }
                )
                continue
            company = code_lookup.get(code, {})
            add_record(
                company_code=code,
                canonical_name=_clean(company.get("canonical_name")) or code,
                short_name=_clean(company.get("short_name")),
                alias=budget_name,
                alias_type="campus_name",
                enabled=int(company.get("status") or 0) == 1,
                source="budget_campus_mapping",
            )
        else:
            unmatched_aliases.append(
                {
                    "alias": _clean(budget_name),
                    "alias_type": "campus_name",
                    "reason": "未能通过已确认实际名称唯一定位公司编码" if not target_codes else "对应多个公司编码",
                    "candidate_company_codes": ",".join(sorted(target_codes)),
                }
            )

    records = _dedupe_records(records)
    conflicts = _detect_conflicts(records)
    return {
        "schema_version": SHARED_NAME_MAPPING_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_system": SHARED_NAME_MAPPING_SOURCE_SYSTEM,
        "records": records,
        "conflicts": conflicts,
        "unmatched_aliases": sorted(unmatched_aliases, key=lambda item: item["alias"]),
        "stats": {
            "record_count": len(records),
            "company_count": len(code_lookup),
            "enabled_record_count": sum(1 for item in records if item.get("enabled", True)),
            "conflict_count": len(conflicts),
            "unmatched_alias_count": len(unmatched_aliases),
        },
    }


def publish_shared_name_mapping_snapshot(path: str | Path | None = None) -> dict[str, Any]:
    snapshot = build_shared_name_mapping_snapshot()
    if snapshot.get("conflicts"):
        raise ValueError("共享名称映射存在启用别名冲突，已阻止发布")

    target = Path(path).expanduser() if path else get_shared_name_mapping_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {**snapshot.get("stats", {}), "path": str(target), "generated_at": snapshot.get("generated_at", "")}
