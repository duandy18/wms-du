# app/oms/platforms/taobao/errors.py
from __future__ import annotations

from typing import Any, Optional


class TaobaoTopError(Exception):
    """OMS 淘宝 / TOP 协议异常基类。"""


class TaobaoTopConfigError(TaobaoTopError):
    """淘宝协议配置缺失或非法。"""


class TaobaoTopProtocolError(TaobaoTopError):
    """TOP 协议层错误，例如 error_response / 缺字段 / envelope 非法。"""

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


class TaobaoTopHttpError(TaobaoTopError):
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
