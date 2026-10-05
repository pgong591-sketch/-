class XGJError(Exception):
    """Base error for 校管家 client failures."""


class XGJConfigError(XGJError):
    """Raised when required local configuration is missing or invalid."""


class XGJAPIError(XGJError):
    """Raised when 校管家 returns a non-success response."""

    def __init__(self, errcode: int | str | None, errmsg: str | None, detail: str = ""):
        self.errcode = errcode
        self.errmsg = errmsg or "校管家接口返回错误"
        self.detail = detail
        message = f"校管家接口错误 errcode={errcode}, errmsg={self.errmsg}"
        if detail:
            message = f"{message}; {detail}"
        super().__init__(message)


class XGJPaginationError(XGJError):
    """Raised when pagination cannot be completed safely."""


class XGJCaptureError(XGJError):
    """Raised when a browser-session capture is missing or inconsistent."""
