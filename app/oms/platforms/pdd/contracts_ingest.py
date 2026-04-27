from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PddOrderIngestRequest(BaseModel):
    start_confirm_at: Optional[str] = Field(
        default=None,
        description="PDD 成交开始时间，格式 yyyy-MM-dd HH:mm:ss；为空时由服务使用默认窗口",
    )
    end_confirm_at: Optional[str] = Field(
        default=None,
        description="PDD 成交结束时间，格式 yyyy-MM-dd HH:mm:ss；为空时由服务使用默认窗口",
    )
    order_status: int = Field(
        default=1,
        ge=1,
        description="PDD 订单状态；默认 1",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="页码，从 1 开始",
    )
    page_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="每页数量，PDD 当前最大 100",
    )


class PddOrderIngestRowOut(BaseModel):
    order_sn: str
    pdd_order_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class PddOrderIngestDataOut(BaseModel):
    platform: str
    store_id: int
    store_code: str
    page: int
    page_size: int
    orders_count: int
    success_count: int
    failed_count: int
    has_more: bool
    start_confirm_at: Optional[str] = None
    end_confirm_at: Optional[str] = None
    rows: List[PddOrderIngestRowOut]


class PddOrderIngestEnvelopeOut(BaseModel):
    ok: bool
    data: PddOrderIngestDataOut
