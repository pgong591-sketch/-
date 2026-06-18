"""Create a safe timestamped backup of the finance SQLite database."""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT_DB = PROJECT_ROOT / "data" / "finance_dw.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups"


def resolve_db_path(value: str | None) -> Path:
    if value:
        return Path(value)
    env_path = os.environ.get("FINANCE_DW_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_PROJECT_DB


def create_backup(source: Path, backup_dir: Path, keep: int | None = None) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{source.stem}_backup_{timestamp}{source.suffix}"

    source_conn = sqlite3.connect(str(source))
    try:
        target_conn = sqlite3.connect(str(target))
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()

    if keep is not None and keep > 0:
        backups = sorted(
            backup_dir.glob(f"{source.stem}_backup_*{source.suffix}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            old_backup.unlink(missing_ok=True)

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the finance SQLite database.")
    parser.add_argument("--db", help="Source database path. Defaults to the D: project database.")
    parser.add_argument("--out-dir", default=str(DEFAULT_BACKUP_DIR), help="Backup directory.")
    parser.add_argument("--keep", type=int, default=30, help="Number of recent backups to keep.")
    args = parser.parse_args()

    source = resolve_db_path(args.db)
    backup_dir = Path(args.out_dir)
    target = create_backup(source, backup_dir, keep=args.keep)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
