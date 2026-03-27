# app/api/routers/platform_shops_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, constr


class PlatformShopCredentialsIn(BaseModel):
    """
    手工录入平台店铺凭据（例如：为了快速联调用，不走 OAuth 流程）。
    """

    platform: constr(strip_whitespace=True, min_length=1, max_length=16)
    shop_id: constr(strip_whitespace=True, min_length=1, max_length=64)

    # 这里用一个通用字段名，底层落到 store_tokens.access_token
    access_token: constr(strip_whitespace=True, min_length=1)

    # 可选：显式传入过期时间。不传的话，我们默认 2 小时后过期。
    token_expires_at: Optional[datetime] = None

    status: Optional[constr(strip_whitespace=True, max_length=32)] = "ACTIVE"

    store_name: Optional[str] = None  # 便于首次接入顺手补录店铺名称


class SimpleOut(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None


class OAuthStartOut(BaseModel):
    ok: bool
    data: Dict[str, Any]


class OAuthCallbackOut(BaseModel):
    ok: bool
    data: Dict[str, Any]
