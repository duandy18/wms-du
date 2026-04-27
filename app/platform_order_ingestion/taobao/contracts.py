# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/taobao/contracts.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class TaobaoTopRequest:
    """
    TOP 调用请求 DTO。

    说明：
    - method 是 TOP API 名
    - biz_params 是业务参数
    - session 为可选授权参数；仅表示请求时携带的协议字段，
      不代表本目录统一承载 OAuth / 店铺授权逻辑
    """

    method: str
    biz_params: Mapping[str, Any]
    session: Optional[str] = None
    version: str = "2.0"
    sign_method: str = "md5"
    format: str = "json"
    partner_id: Optional[str] = None
    simplify: bool = True


@dataclass(frozen=True)
class TaobaoTopResponse:
    """
    TOP 返回 DTO。

    raw 为原始 JSON。
    body 为剥离 error_response 后的成功体。
    """

    raw: Dict[str, Any]
    body: Dict[str, Any] = field(default_factory=dict)
