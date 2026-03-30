# app/oms/platforms/pdd/contracts_mock.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


PddMockScenario = Literal["normal", "address_missing", "item_abnormal", "mixed"]


class PddMockAuthorizeRequest(BaseModel):
    granted_identity_display: Optional[str] = Field(
        default=None,
        description="授权展示名；为空时默认使用 shop_id",
    )
    access_token: Optional[str] = Field(
        default=None,
        description="可选，默认自动生成 mock token",
    )
    expires_in_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description="mock token 过期天数",
    )


class PddMockIngestOrdersRequest(BaseModel):
    scenario: PddMockScenario = Field(
        default="mixed",
        description="生成场景：normal / address_missing / item_abnormal / mixed",
    )
    count: int = Field(
        default=6,
        ge=1,
        le=100,
        description="生成订单数量",
    )


class PddMockClearOrdersRequest(BaseModel):
    clear_connection: bool = Field(
        default=False,
        description="是否同时清理连接状态",
    )
    clear_credential: bool = Field(
        default=False,
        description="是否同时清理凭据",
    )
