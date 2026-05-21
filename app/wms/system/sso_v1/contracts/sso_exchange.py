# app/wms/system/sso_v1/contracts/sso_exchange.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSsoExchangeIn(_Base):
    code: str = Field(..., min_length=1, max_length=256)
    state: str = Field(..., min_length=1, max_length=256)


class WmsSsoExchangeOut(_Base):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    redirect_path: str = "/"


class ErpSsoAuthorizationCodeConsumeOut(_Base):
    app_code: str
    sub: str
    erp_user_id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    redirect_path: str


__all__ = [
    "ErpSsoAuthorizationCodeConsumeOut",
    "WmsSsoExchangeIn",
    "WmsSsoExchangeOut",
]
