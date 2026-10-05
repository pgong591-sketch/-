from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Callable

import polars as pl
import requests

from .auth import TokenProvider, XGJConfig, redact_mapping
from .capture import consume_details_capture_path, load_consume_details_capture
from .entities import XGJEndpoint
from .exceptions import XGJAPIError, XGJCaptureError, XGJPaginationError

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class XGJClient:
    def __init__(
        self,
        config: XGJConfig | None = None,
        *,
        session: requests.Session | None = None,
        transport: Transport | None = None,
    ):
        self.config = config or XGJConfig.from_env()
        self.session = session or requests.Session()
        self.token_provider = TokenProvider(self.config, self.session)
        self.transport = transport

    def get_consume_details(
        self,
        start_date: str | date,
        end_date: str | date,
        *,
        page_size: int | None = None,
        max_pages: int = 10000,
    ) -> pl.DataFrame:
        start_iso = _to_iso_date(start_date)
        end_iso = _to_iso_date(end_date)
        if start_iso > end_iso:
            raise ValueError("start_date 不能晚于 end_date")

        source = self.config.source
        if source not in {"auto", "official_api", "browser_capture"}:
            raise ValueError("XGJ_SOURCE 只能是 auto、official_api 或 browser_capture")

        capture_path = consume_details_capture_path(
            self.config.capture_dir,
            start_iso,
            end_iso,
        )
        if self.transport is None and source != "official_api" and capture_path.is_file():
            return load_consume_details_capture(
                capture_path,
                start_date=start_iso,
                end_date=end_iso,
            )
        if self.transport is None and source == "browser_capture":
            raise XGJCaptureError(f"没有找到对应日期的浏览器取数文件：{capture_path}")

        start = start_iso.replace("-", "")
        end = end_iso.replace("-", "")

        size = page_size or self.config.page_size
        if size <= 0 or size > 100:
            raise ValueError("校管家课消批量接口 page_size 最大为 100")

        rows: list[dict[str, Any]] = []
        page_value = 0
        seen_page_values: set[int] = set()
        expected_total: int | None = None

        for _ in range(max_pages):
            if page_value in seen_page_values:
                raise XGJPaginationError(f"分页参数重复，已停止：{page_value}")
            seen_page_values.add(page_value)

            payload = self._get(
                XGJEndpoint.CONSUME_DETAILS_BATCH.value,
                {
                    "updatetime": start,
                    "updateTimeEnd": end,
                    "offset": page_value,
                    "size": size,
                },
            )

            page_rows = payload.get("data") or []
            if not isinstance(page_rows, list):
                raise XGJAPIError(payload.get("errcode"), payload.get("errmsg"), "data 不是列表")
            rows.extend(page_rows)

            if expected_total is None and payload.get("count_number") is not None:
                expected_total = int(payload["count_number"])

            has_more = int(payload.get("has_more") or 0)
            if not has_more:
                break

            if not page_rows:
                raise XGJPaginationError("接口提示还有下一页，但当前页为空，已停止以避免无限循环")

            page_value = page_value + 1 if self.config.page_mode == "page" else page_value + size
            time.sleep(self.config.min_request_interval_seconds)
        else:
            raise XGJPaginationError(f"超过最大分页次数 {max_pages}，已停止")

        if expected_total is not None and len(rows) != expected_total:
            raise XGJPaginationError(f"分页条数不一致：已取 {len(rows)} 行，接口总数 {expected_total} 行")

        return pl.DataFrame(rows)

    def get_students(self) -> pl.DataFrame:
        raise NotImplementedError("已预留，当前最小闭环先稳定 get_consume_details()。")

    def get_courses(self) -> pl.DataFrame:
        raise NotImplementedError("已预留，当前最小闭环先稳定 get_consume_details()。")

    def get_classes(self) -> pl.DataFrame:
        raise NotImplementedError("已预留，当前最小闭环先稳定 get_consume_details()。")

    def get_orders(self) -> pl.DataFrame:
        raise NotImplementedError("已预留，当前最小闭环先稳定 get_consume_details()。")

    def get_payments(self) -> pl.DataFrame:
        raise NotImplementedError("已预留，当前最小闭环先稳定 get_consume_details()。")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        access_token = self.token_provider.get_access_token()
        all_params = {"access_token": access_token, **params}

        if self.transport:
            payload = self.transport(path, all_params)
        else:
            response = self.session.get(
                f"{self.config.base_url}{path}",
                params=all_params,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()

        errcode = payload.get("errcode")
        if errcode not in (0, "0", None):
            safe_params = redact_mapping(all_params)
            raise XGJAPIError(errcode, payload.get("errmsg"), f"path={path}, params={safe_params}")
        return payload


def _to_yyyymmdd(value: str | date) -> str:
    return _to_iso_date(value).replace("-", "")


def _to_iso_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if "-" in value:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    return datetime.strptime(value, "%Y%m%d").date().isoformat()
