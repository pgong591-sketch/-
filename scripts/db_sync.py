"""
Create and restore portable SQLite database snapshots.

This script is intentionally snapshot-based. It does not run the live database
from a cloud folder, and it does not attempt to merge two independently edited
SQLite files.

Typical setup:
    python scripts/db_sync.py init --sync-dir D:\\finance_dw_sync --machine office

Office/home handoff:
    python scripts/db_sync.py push --note "leaving office"
    python scripts/db_sync.py pull
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "finance_dw.db"
LOCAL_CONFIG = ROOT / ".dbsync.local.json"
DEFAULT_STATE = ROOT / "data" / ".db_sync_state.json"
PACKAGE_PREFIX = "finance_dw_snapshot_"
PACKAGE_SUFFIX = ".zip"
MANIFEST_NAME = "manifest.json"
DB_ENTRY_NAME = "finance_dw.db"
SNAPSHOT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Snapshot:
    path: Path
    manifest: dict[str, Any]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    temp.replace(path)


def resolve_sync_dir(args: argparse.Namespace) -> Path:
    if args.sync_dir:
        return Path(args.sync_dir).expanduser().resolve()

    env_value = os.environ.get("FINANCE_DW_SYNC_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()

    config = load_json(LOCAL_CONFIG)
    if config.get("sync_dir"):
        return Path(config["sync_dir"]).expanduser().resolve()

    raise SystemExit(
        "Sync directory is not configured. Run: "
        "python scripts/db_sync.py init --sync-dir <shared-folder>"
    )


def resolve_machine(args: argparse.Namespace) -> str:
    if args.machine:
        return clean_token(args.machine)
    env_value = os.environ.get("FINANCE_DW_MACHINE")
    if env_value:
        return clean_token(env_value)
    config = load_json(LOCAL_CONFIG)
    if config.get("machine"):
        return clean_token(config["machine"])
    return clean_token(socket.gethostname())


def resolve_state_path(args: argparse.Namespace, db_path: Path) -> Path:
    if args.state:
        return Path(args.state).expanduser().resolve()

    try:
        if db_path.resolve() == DEFAULT_DB.resolve():
            return DEFAULT_STATE
    except OSError:
        pass
    return db_path.parent / ".db_sync_state.json"


def clean_token(value: str) -> str:
    result = []
    for char in str(value).strip():
        if char.isalnum() or char in ("-", "_"):
            result.append(char)
        else:
            result.append("_")
    token = "".join(result).strip("_")
    return token or "machine"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_integrity_check(db_path: Path) -> None:
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise SystemExit(f"SQLite integrity check failed: {exc}") from exc

    if not result or result[0] != "ok":
        raise SystemExit(f"SQLite integrity check failed: {result[0] if result else 'no result'}")


def table_counts(db_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for (table_name,) in rows:
            quoted = table_name.replace('"', '""')
            try:
                counts[table_name] = int(
                    conn.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
                )
            except sqlite3.DatabaseError:
                counts[table_name] = -1
    finally:
        conn.close()
    return counts


def sqlite_user_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def backup_sqlite_to_file(source_db: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(source_db), timeout=30)
    try:
        dest = sqlite3.connect(str(target_db))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def read_manifest(package_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(package_path, "r") as zf:
        with zf.open(MANIFEST_NAME) as fh:
            return json.loads(fh.read().decode("utf-8"))


def find_snapshots(sync_dir: Path) -> list[Snapshot]:
    if not sync_dir.exists():
        return []

    snapshots: list[Snapshot] = []
    for path in sync_dir.glob(f"{PACKAGE_PREFIX}*{PACKAGE_SUFFIX}"):
        try:
            manifest = read_manifest(path)
        except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile):
            continue
        snapshots.append(Snapshot(path=path, manifest=manifest))

    snapshots.sort(
        key=lambda item: (
            str(item.manifest.get("created_at_utc", "")),
            item.path.stat().st_mtime,
        ),
        reverse=True,
    )
    return snapshots


def latest_snapshot(sync_dir: Path) -> Snapshot:
    snapshots = find_snapshots(sync_dir)
    if not snapshots:
        raise SystemExit(f"No snapshots found in {sync_dir}")
    return snapshots[0]


def command_init(args: argparse.Namespace) -> int:
    sync_dir = Path(args.sync_dir).expanduser().resolve()
    machine = resolve_machine(args)
    sync_dir.mkdir(parents=True, exist_ok=True)
    save_json(
        LOCAL_CONFIG,
        {
            "sync_dir": str(sync_dir),
            "machine": machine,
        },
    )
    print(f"Configured sync_dir: {sync_dir}")
    print(f"Configured machine: {machine}")
    print(f"Local config: {LOCAL_CONFIG}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    sync_dir = resolve_sync_dir(args)
    state_path = resolve_state_path(args, db_path)
    state = load_json(state_path)
    print(f"Database: {db_path}")
    if db_path.exists():
        print(f"Local size: {db_path.stat().st_size}")
        print(f"Local sha256: {sha256_file(db_path)}")
    else:
        print("Local database: missing")

    print(f"Sync dir: {sync_dir}")
    snapshots = find_snapshots(sync_dir)
    if snapshots:
        latest = snapshots[0]
        print(f"Latest snapshot: {latest.path.name}")
        print(f"Latest id: {latest.manifest.get('snapshot_id', '')}")
        print(f"Latest machine: {latest.manifest.get('source_machine', '')}")
        print(f"Latest sha256: {latest.manifest.get('db_sha256', '')}")
    else:
        print("Latest snapshot: none")

    if state:
        print(f"State file: {state_path}")
        print(f"Last pulled: {state.get('last_pulled_snapshot_id', '')}")
        print(f"Last pushed: {state.get('last_pushed_snapshot_id', '')}")
    else:
        print("Local sync state: empty")
    return 0


def command_list(args: argparse.Namespace) -> int:
    sync_dir = resolve_sync_dir(args)
    snapshots = find_snapshots(sync_dir)
    limit = max(args.limit, 1)
    if not snapshots:
        print(f"No snapshots found in {sync_dir}")
        return 0
    for item in snapshots[:limit]:
        manifest = item.manifest
        print(
            f"{manifest.get('created_at_utc', '')}  "
            f"{manifest.get('source_machine', '')}  "
            f"{manifest.get('db_sha256', '')[:12]}  "
            f"{item.path.name}"
        )
    return 0


def command_push(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    sync_dir = resolve_sync_dir(args)
    machine = resolve_machine(args)
    state_path = resolve_state_path(args, db_path)

    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    sync_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="finance_dw_sync_") as temp_dir:
        temp_db = Path(temp_dir) / DB_ENTRY_NAME
        backup_sqlite_to_file(db_path, temp_db)
        sqlite_integrity_check(temp_db)

        db_hash = sha256_file(temp_db)
        stamp = utc_stamp()
        snapshot_id = f"{stamp}_{machine}_{db_hash[:12]}"
        package_name = f"{PACKAGE_PREFIX}{snapshot_id}{PACKAGE_SUFFIX}"
        package_path = sync_dir / package_name
        temp_package = Path(temp_dir) / package_name
        manifest = {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "snapshot_id": snapshot_id,
            "created_at_utc": stamp,
            "source_machine": machine,
            "db_entry": DB_ENTRY_NAME,
            "db_sha256": db_hash,
            "db_size": temp_db.stat().st_size,
            "db_user_version": sqlite_user_version(temp_db),
            "table_counts": table_counts(temp_db),
            "note": args.note or "",
        }

        with zipfile.ZipFile(temp_package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(temp_db, DB_ENTRY_NAME)
            zf.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        package_staging = package_path.with_suffix(package_path.suffix + ".tmp")
        shutil.copy2(temp_package, package_staging)
        package_staging.replace(package_path)

    state = load_json(state_path)
    state.update(
        {
            "last_pushed_snapshot_id": snapshot_id,
            "last_pushed_hash": db_hash,
            "last_seen_snapshot_id": snapshot_id,
            "last_seen_hash": db_hash,
            "updated_at_utc": utc_stamp(),
        }
    )
    save_json(state_path, state)

    print(f"Pushed snapshot: {package_path}")
    print(f"Snapshot id: {snapshot_id}")
    print(f"Database sha256: {db_hash}")
    return 0


def extract_db_from_snapshot(snapshot: Snapshot, target: Path) -> dict[str, Any]:
    manifest = snapshot.manifest
    db_entry = manifest.get("db_entry", DB_ENTRY_NAME)
    with zipfile.ZipFile(snapshot.path, "r") as zf:
        with zf.open(db_entry) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return manifest


def command_pull(args: argparse.Namespace) -> int:
    db_path = Path(args.db).expanduser().resolve()
    sync_dir = resolve_sync_dir(args)
    state_path = resolve_state_path(args, db_path)
    snapshot = latest_snapshot(sync_dir)
    manifest = snapshot.manifest
    remote_hash = str(manifest.get("db_sha256", ""))
    if not remote_hash:
        raise SystemExit(f"Snapshot missing db_sha256: {snapshot.path}")

    local_hash = sha256_file(db_path) if db_path.exists() else ""
    if local_hash == remote_hash:
        state = load_json(state_path)
        state.update(
            {
                "last_pulled_snapshot_id": manifest.get("snapshot_id", ""),
                "last_pulled_hash": remote_hash,
                "last_seen_snapshot_id": manifest.get("snapshot_id", ""),
                "last_seen_hash": remote_hash,
                "updated_at_utc": utc_stamp(),
            }
        )
        save_json(state_path, state)
        print("Local database already matches latest snapshot.")
        print(f"Snapshot id: {manifest.get('snapshot_id', '')}")
        return 0

    state = load_json(state_path)
    known_hashes = {
        str(state.get("last_pulled_hash", "")),
        str(state.get("last_pushed_hash", "")),
        str(state.get("last_seen_hash", "")),
        "",
    }
    if local_hash and local_hash not in known_hashes and not args.force:
        print("Local database has changes that were not created by the last sync action.")
        print(f"Local sha256:  {local_hash}")
        print(f"Remote sha256: {remote_hash}")
        print("Refusing to overwrite. Re-run with --force after checking the local backup plan.")
        return 2

    with tempfile.TemporaryDirectory(prefix="finance_dw_pull_") as temp_dir:
        extracted_db = Path(temp_dir) / DB_ENTRY_NAME
        extract_db_from_snapshot(snapshot, extracted_db)
        actual_hash = sha256_file(extracted_db)
        if actual_hash != remote_hash:
            raise SystemExit(
                f"Snapshot hash mismatch. Expected {remote_hash}, got {actual_hash}"
            )
        sqlite_integrity_check(extracted_db)

        if db_path.exists():
            backup_dir = db_path.parent / "backups" / "db_sync"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_name = (
                f"{db_path.stem}_before_pull_{utc_stamp()}_"
                f"{local_hash[:12] or 'missing'}{db_path.suffix}"
            )
            backup_path = backup_dir / backup_name
            shutil.copy2(db_path, backup_path)
            print(f"Backed up local database: {backup_path}")

        db_path.parent.mkdir(parents=True, exist_ok=True)
        temp_target = db_path.with_suffix(db_path.suffix + ".sync_tmp")
        shutil.copy2(extracted_db, temp_target)
        temp_target.replace(db_path)

    state.update(
        {
            "last_pulled_snapshot_id": manifest.get("snapshot_id", ""),
            "last_pulled_hash": remote_hash,
            "last_seen_snapshot_id": manifest.get("snapshot_id", ""),
            "last_seen_hash": remote_hash,
            "updated_at_utc": utc_stamp(),
        }
    )
    save_json(state_path, state)

    print(f"Pulled snapshot: {snapshot.path.name}")
    print(f"Snapshot id: {manifest.get('snapshot_id', '')}")
    print(f"Database sha256: {remote_hash}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to finance_dw.db")
    parser.add_argument("--sync-dir", help="Shared snapshot directory")
    parser.add_argument("--machine", help="Stable name for this computer")
    parser.add_argument("--state", help="Local sync state file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_cmd = subparsers.add_parser("init", help="Save local sync settings")
    init_cmd.add_argument("--sync-dir", required=True, help="Shared snapshot directory")
    init_cmd.add_argument("--machine", help="Stable name for this computer")
    init_cmd.set_defaults(func=command_init)

    status_cmd = subparsers.add_parser("status", help="Show local and remote state")
    status_cmd.set_defaults(func=command_status)

    list_cmd = subparsers.add_parser("list", help="List recent snapshots")
    list_cmd.add_argument("--limit", type=int, default=10)
    list_cmd.set_defaults(func=command_list)

    push_cmd = subparsers.add_parser("push", help="Publish current DB as a snapshot")
    push_cmd.add_argument("--note", default="", help="Optional snapshot note")
    push_cmd.set_defaults(func=command_push)

    pull_cmd = subparsers.add_parser("pull", help="Restore latest DB snapshot")
    pull_cmd.add_argument(
        "--force",
        action="store_true",
        help="Overwrite local DB even if it has unsynced local changes",
    )
    pull_cmd.set_defaults(func=command_pull)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
