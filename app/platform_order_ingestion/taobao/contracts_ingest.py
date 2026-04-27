# Module split: Taobao platform order native ingest API contracts.
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TaobaoOrderIngestRequest(BaseModel):
    start_time: Optional[str] = Field(default=None)
    end_time: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class TaobaoOrderIngestRowOut(BaseModel):
    tid: str
    taobao_order_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class TaobaoOrderIngestDataOut(BaseModel):
    platform: str
    store_id: int
    store_code: str
    page: int
    page_size: int
    orders_count: int
    success_count: int
    failed_count: int
    has_more: bool
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    rows: List[TaobaoOrderIngestRowOut]


class TaobaoOrderIngestEnvelopeOut(BaseModel):
    ok: bool
    data: TaobaoOrderIngestDataOut
