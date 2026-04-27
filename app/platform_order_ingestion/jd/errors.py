# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/errors.py
from __future__ import annotations

from typing import Any, Optional


class JdJosError(Exception):
    """OMS 京东 / JOS 协议异常基类。"""


class JdJosConfigError(JdJosError):
    """京东协议配置缺失或非法。"""


class JdJosProtocolError(JdJosError):
    """JOS 协议层错误，例如错误 envelope / 缺字段 / 返回体非法。"""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        payload: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload


class JdJosHttpError(JdJosError):
    """HTTP 层错误。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
