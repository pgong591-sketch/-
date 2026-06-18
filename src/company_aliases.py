"""Company alias resolution helpers.

Company names in source Excel files are often short names. This module keeps
that mapping configurable through the database while still allowing callers to
fall back to their existing legacy mappings during migration.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy import text

from .db_connection import get_session


def ensure_company_alias_table() -> None:
    """Create the alias table when an older SQLite database is in use."""
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS company_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                company_code TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                status INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_company_aliases_alias
                ON company_aliases(alias)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_company_aliases_company
                ON company_aliases(company_code)
        """))
        session.commit()
    finally:
        session.close()


def upsert_company_alias(
    alias: str,
    company_code: str,
    source: str = "manual",
    status: int = 1,
    on_conflict: str = "raise",
) -> bool:
    """Create or update one alias mapping.

    Args:
        alias: Raw alias or source-system company name.
        company_code: Canonical code in ``companies``.
        source: Mapping source marker, for example ``companies`` or ``import``.
        status: Active flag.
        on_conflict: ``raise`` to reject aliases mapped to another company, or
            ``skip`` to leave the existing mapping unchanged.

    Returns:
        True when a row was inserted or updated, False when it was skipped.
    """
    raw_alias = str(alias or "").strip()
    canonical_code = str(company_code or "").strip()
    if not raw_alias or not canonical_code:
        return False
    if on_conflict not in {"raise", "skip"}:
        raise ValueError("on_conflict must be 'raise' or 'skip'")

    ensure_company_alias_table()
    session = get_session()
    try:
        existing = session.execute(
            text("""
                SELECT company_code, source
                FROM company_aliases
                WHERE alias = :alias
            """),
            {"alias": raw_alias},
        ).fetchone()

        if existing and str(existing[0]).strip() != canonical_code:
            if on_conflict == "skip":
                return False
            raise ValueError(
                f"Alias {raw_alias!r} already maps to {existing[0]!r}, "
                f"cannot map it to {canonical_code!r}"
            )

        if existing:
            session.execute(
                text("""
                    UPDATE company_aliases
                    SET company_code = :company_code,
                        source = :source,
                        status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE alias = :alias
                """),
                {
                    "alias": raw_alias,
                    "company_code": canonical_code,
                    "source": source or existing[1] or "manual",
                    "status": status,
                },
            )
        else:
            session.execute(
                text("""
                    INSERT INTO company_aliases
                        (alias, company_code, source, status)
                    VALUES
                        (:alias, :company_code, :source, :status)
                """),
                {
                    "alias": raw_alias,
                    "company_code": canonical_code,
                    "source": source or "manual",
                    "status": status,
                },
            )
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def seed_aliases_from_companies() -> int:
    """Populate aliases from company code, full name, and short name."""
    ensure_company_alias_table()
    session = get_session()
    inserted = 0
    try:
        companies = session.execute(text("""
            SELECT code, name, short_name
            FROM companies
            WHERE status = 1
        """)).fetchall()
        for code, name, short_name in companies:
            aliases = {str(code).strip()}
            if name:
                aliases.add(str(name).strip())
            if short_name:
                aliases.add(str(short_name).strip())
            for alias in aliases:
                if not alias:
                    continue
                existing = session.execute(
                    text("SELECT company_code FROM company_aliases WHERE alias = :alias"),
                    {"alias": alias},
                ).fetchone()
                if existing and str(existing[0]).strip() != str(code).strip():
                    continue
                result = session.execute(text("""
                    INSERT INTO company_aliases
                        (alias, company_code, source, status)
                    VALUES
                        (:alias, :company_code, 'companies', 1)
                    ON CONFLICT(alias) DO UPDATE SET
                        company_code = excluded.company_code,
                        status = 1,
                        updated_at = CURRENT_TIMESTAMP
                """), {"alias": alias, "company_code": code})
                inserted += result.rowcount or 0
        session.commit()
        return inserted
    finally:
        session.close()


def get_company_alias_map() -> Dict[str, str]:
    """Return active alias -> company_code mappings."""
    ensure_company_alias_table()
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT alias, company_code
            FROM company_aliases
            WHERE status = 1
        """)).fetchall()
        return {str(alias).strip(): str(code).strip() for alias, code in rows if alias and code}
    finally:
        session.close()


def resolve_company_code(raw_name: str) -> Tuple[Optional[str], str]:
    """Resolve a raw source company name to a company code."""
    raw = str(raw_name or "").strip()
    if not raw:
        return None, "none"

    aliases = get_company_alias_map()
    if raw in aliases:
        return aliases[raw], "alias"

    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT code, name, short_name
            FROM companies
            WHERE status = 1
        """)).fetchall()

        exact = {}
        for code, name, short_name in rows:
            exact[str(code).strip()] = str(code).strip()
            if name:
                exact[str(name).strip()] = str(code).strip()
            if short_name:
                exact[str(short_name).strip()] = str(code).strip()
        if raw in exact:
            return exact[raw], "company_exact"

        candidates = []
        for code, name, short_name in rows:
            for candidate in [name, short_name]:
                candidate = str(candidate or "").strip()
                if candidate and (raw in candidate or candidate in raw):
                    candidates.append((len(candidate), str(code).strip()))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1], "company_fuzzy"

        return None, "none"
    finally:
        session.close()
