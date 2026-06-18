"""Import the annual budget workbook into normalized budget tables."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.budget_importer import import_budget_workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Import annual budget workbook")
    parser.add_argument("file", help="Path to budget workbook")
    parser.add_argument("--year", help="Budget year, e.g. 2026")
    parser.add_argument("--keep-existing", action="store_true", help="Do not delete existing rows for the year first")
    args = parser.parse_args()

    result = import_budget_workbook(
        args.file,
        budget_year=args.year,
        replace=not args.keep_existing,
    )
    print(result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
