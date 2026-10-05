from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from .exceptions import XGJAPIError, XGJConfigError


SENSITIVE_PARAM_NAMES = {
    "access_token",
    "appid",
    "secret",
    "appsecret",
    "authorization",
    "cookie",
    "token",
}


@dataclass(frozen=True)
class XGJConfig:
    base_url: str = "https://api.xiaogj.com"
    appid: str | None = None
    appsecret: str | None = None
    access_token: str | None = None
    timeout_seconds: float = 30.0
    page_size: int = 100
    page_mode: str = "offset"
    min_request_interval_seconds: float = 0.2
    source: str = "auto"
    capture_dir: Path = Path("xgj_runtime")

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "XGJConfig":
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        return cls(
            base_url=os.getenv("XGJ_API_BASE_URL", cls.base_url).rstrip("/"),
            appid=os.getenv("XGJ_APPID") or None,
            appsecret=os.getenv("XGJ_APPSECRET") or None,
            access_token=os.getenv("XGJ_ACCESS_TOKEN") or None,
            timeout_seconds=float(os.getenv("XGJ_TIMEOUT_SECONDS", cls.timeout_seconds)),
            page_size=int(os.getenv("XGJ_PAGE_SIZE", cls.page_size)),
            page_mode=os.getenv("XGJ_PAGE_MODE", cls.page_mode),
            min_request_interval_seconds=float(
                os.getenv("XGJ_MIN_REQUEST_INTERVAL_SECONDS", cls.min_request_interval_seconds)
            ),
            source=os.getenv("XGJ_SOURCE", cls.source).lower(),
            capture_dir=Path(os.getenv("XGJ_CAPTURE_DIR", str(cls.capture_dir))),
        )

    def validate_for_api(self) -> None:
        if self.access_token:
            return
        if self.appid and self.appsecret:
            return
        raise XGJConfigError(
            "缺少校管家官方 API 凭证。请在本地 .env 配置 XGJ_APPID/XGJ_APPSECRET，"
            "或临时配置 XGJ_ACCESS_TOKEN。不要把这些值提交到 Git。"
        )


class TokenProvider:
    def __init__(self, config: XGJConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self._token = config.access_token
        self._expires_at = 0.0 if not config.access_token else float("inf")

    def get_access_token(self) -> str:
        self.config.validate_for_api()
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        if not (self.config.appid and self.config.appsecret):
            raise XGJConfigError("当前 access_token 已过期或不可刷新，请配置 XGJ_APPID/XGJ_APPSECRET。")

        response = self.session.get(
            f"{self.config.base_url}/token",
            params={"appid": self.config.appid, "secret": self.config.appsecret},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        errcode = payload.get("errcode")
        if errcode not in (0, "0", None):
            raise XGJAPIError(errcode, payload.get("errmsg"), "获取 access_token 失败")

        token = payload.get("access_token")
        if not token:
            raise XGJAPIError(errcode, payload.get("errmsg"), "响应中没有 access_token")

        expires_in = int(payload.get("expires_in") or 7200)
        self._token = token
        self._expires_at = time.time() + expires_in
        return token


def redact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if key.lower() in SENSITIVE_PARAM_NAMES:
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted
