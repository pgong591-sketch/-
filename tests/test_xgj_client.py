import json

import polars as pl
import pytest

from xgj_client import XGJCaptureError, XGJClient, XGJConfig, XGJPaginationError


def test_get_consume_details_reads_all_pages():
    calls = []
    pages = {
        0: {
            "errcode": 0,
            "has_more": 1,
            "count_number": 3,
            "data": [{"id": "1", "time": "20260831090000"}, {"id": "2", "time": "20260901090000"}],
        },
        2: {
            "errcode": 0,
            "has_more": 0,
            "count_number": 3,
            "data": [{"id": "3", "time": "20260906090000"}],
        },
    }

    def transport(path, params):
        calls.append((path, params.copy()))
        return pages[params["offset"]]

    client = XGJClient(
        XGJConfig(access_token="runtime-token", page_size=2, min_request_interval_seconds=0),
        transport=transport,
    )

    df = client.get_consume_details("2026-08-31", "2026-09-06")

    assert isinstance(df, pl.DataFrame)
    assert df.shape == (3, 2)
    assert df["id"].to_list() == ["1", "2", "3"]
    assert [params["offset"] for _, params in calls] == [0, 2]
    assert all(params["access_token"] == "runtime-token" for _, params in calls)


def test_get_consume_details_stops_on_count_mismatch():
    def transport(path, params):
        return {
            "errcode": 0,
            "has_more": 0,
            "count_number": 2,
            "data": [{"id": "1"}],
        }

    client = XGJClient(XGJConfig(access_token="runtime-token"), transport=transport)

    with pytest.raises(XGJPaginationError, match="分页条数不一致"):
        client.get_consume_details("2026-08-31", "2026-09-06")


def test_get_consume_details_loads_verified_browser_capture(tmp_path):
    capture = tmp_path / "xgj_consume_details_20260831_20260906.json"
    capture.write_text(
        json.dumps(
            {
                "meta": {
                    "start_date": "2026-08-31",
                    "end_date": "2026-09-06",
                    "total_count": 2,
                    "fetched_count": 2,
                },
                "data": [{"id": "1", "Date": "2026-08-31"}, {"id": "2", "Date": "2026-09-06"}],
            }
        ),
        encoding="utf-8",
    )
    client = XGJClient(XGJConfig(source="browser_capture", capture_dir=tmp_path))

    df = client.get_consume_details("2026-08-31", "2026-09-06")

    assert df.shape == (2, 2)
    assert df["id"].to_list() == ["1", "2"]


def test_browser_capture_rejects_count_mismatch(tmp_path):
    capture = tmp_path / "xgj_consume_details_20260831_20260906.json"
    capture.write_text(
        json.dumps(
            {
                "meta": {
                    "start_date": "2026-08-31",
                    "end_date": "2026-09-06",
                    "total_count": 2,
                    "fetched_count": 1,
                },
                "data": [{"id": "1"}],
            }
        ),
        encoding="utf-8",
    )
    client = XGJClient(XGJConfig(source="browser_capture", capture_dir=tmp_path))

    with pytest.raises(XGJCaptureError, match="分页条数不一致"):
        client.get_consume_details("2026-08-31", "2026-09-06")


def test_browser_capture_rejects_out_of_range_class_date(tmp_path):
    capture = tmp_path / "xgj_consume_details_20260831_20260906.json"
    capture.write_text(
        json.dumps(
            {
                "meta": {
                    "start_date": "2026-08-31",
                    "end_date": "2026-09-06",
                    "total_count": 1,
                    "fetched_count": 1,
                },
                "data": [{"StartTime": "2026-09-07 09:00~10:00"}],
            }
        ),
        encoding="utf-8",
    )
    client = XGJClient(XGJConfig(source="browser_capture", capture_dir=tmp_path))

    with pytest.raises(XGJCaptureError, match="上课日期越界"):
        client.get_consume_details("2026-08-31", "2026-09-06")
