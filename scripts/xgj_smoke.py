from pathlib import Path
import sys

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xgj_client import XGJClient, XGJError


SAFE_PREVIEW_COLUMNS = [
    "CampusName",
    "CourseSubject",
    "Subject",
    "StartTime",
    "TimeLong",
    "Amount",
    "ConsumeMoney",
    "Date",
    "TypeName",
    "ProductType",
]


def main() -> None:
    client = XGJClient()
    try:
        df = client.get_consume_details("2026-08-31", "2026-09-06")
    except XGJError as exc:
        raise SystemExit(str(exc)) from exc

    print(df.shape)
    print(df.columns)
    preview_columns = [column for column in SAFE_PREVIEW_COLUMNS if column in df.columns]
    print(df.select(preview_columns).head() if preview_columns else "没有可安全预览的列")

    if "StartTime" in df.columns and not df.is_empty():
        print(
            df.select(
                pl.col("StartTime").cast(pl.String).str.slice(0, 10).min().alias("min_date"),
                pl.col("StartTime").cast(pl.String).str.slice(0, 10).max().alias("max_date"),
            )
        )
    elif "time" in df.columns and not df.is_empty():
        print(
            df.select(
                pl.col("time").cast(pl.String).str.slice(0, 8).min().alias("min_date"),
                pl.col("time").cast(pl.String).str.slice(0, 8).max().alias("max_date"),
            )
        )


if __name__ == "__main__":
    main()
