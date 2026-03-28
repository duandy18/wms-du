# app/oms/platforms/taobao/__init__.py
"""
OMS / 淘宝平台接入域。

职责：
- 承载 OMS 淘宝接入相关协议与业务实现
- 包含 settings / sign / client / contracts
- 不与 TMS 共用授权模型
"""

from .contracts import TaobaoTopRequest, TaobaoTopResponse
from .errors import (
    TaobaoTopConfigError,
    TaobaoTopError,
    TaobaoTopHttpError,
    TaobaoTopProtocolError,
)
from .settings import TaobaoTopConfig
from .top_client import TaobaoTopClient
from .top_sign import build_top_sign

__all__ = [
    "TaobaoTopConfig",
    "TaobaoTopRequest",
    "TaobaoTopResponse",
    "TaobaoTopClient",
    "TaobaoTopConfigError",
    "TaobaoTopError",
    "TaobaoTopHttpError",
    "TaobaoTopProtocolError",
    "build_top_sign",
]
