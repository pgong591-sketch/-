from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from .exceptions import XGJCaptureError


def consume_details_capture_path(
    capture_dir: str | Path,
    start_date: str,
    end_date: str,
) -> Path:
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    return Path(capture_dir) / f"xgj_consume_details_{start}_{end}.json"


def load_consume_details_capture(
    path: str | Path,
    *,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    capture_path = Path(path)
    try:
        with capture_path.open("r", encoding="utf-8") as handle:
            payload: Any = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise XGJCaptureError(f"无法读取校管家浏览器取数文件：{capture_path}") from exc

    if not isinstance(payload, dict):
        raise XGJCaptureError("校管家浏览器取数文件顶层必须是对象")

    meta = payload.get("meta")
    rows = payload.get("data")
    if not isinstance(meta, dict) or not isinstance(rows, list):
        raise XGJCaptureError("校管家浏览器取数文件缺少 meta 或 data")
    if meta.get("start_date") != start_date or meta.get("end_date") != end_date:
        raise XGJCaptureError(
            "浏览器取数文件日期不匹配："
            f"文件为 {meta.get('start_date')} 至 {meta.get('end_date')}，"
            f"请求为 {start_date} 至 {end_date}"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise XGJCaptureError("校管家浏览器取数文件包含非对象数据行")

    try:
        total_count = int(meta["total_count"])
        fetched_count = int(meta["fetched_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise XGJCaptureError("校管家浏览器取数文件缺少有效的条数校验信息") from exc

    if total_count != fetched_count or fetched_count != len(rows):
        raise XGJCaptureError(
            "浏览器分页条数不一致："
            f"接口总数 {total_count}，记录数 {fetched_count}，实际行数 {len(rows)}"
        )

    if not rows:
        return pl.DataFrame()

    frame = pl.from_dicts(rows, infer_schema_length=None, strict=False)
    if "StartTime" in frame.columns:
        class_dates = (
            frame.select(
                pl.col("StartTime")
                .cast(pl.String)
                .str.slice(0, 10)
                .alias("class_date")
            )
            .filter(pl.col("class_date").str.contains(r"^\d{4}-\d{2}-\d{2}$"))
        )
        if not class_dates.is_empty():
            min_date = class_dates["class_date"].min()
            max_date = class_dates["class_date"].max()
            if min_date < start_date or max_date > end_date:
                raise XGJCaptureError(
                    f"浏览器取数文件上课日期越界：{min_date} 至 {max_date}"
                )

    return frame
