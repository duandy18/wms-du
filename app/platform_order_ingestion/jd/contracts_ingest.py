# Module split: JD platform order native ingest API contracts.
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class JdOrderIngestRequest(BaseModel):
    start_time: Optional[str] = Field(default=None)
    end_time: Optional[str] = Field(default=None)
    order_state: Optional[str] = Field(default=None)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class JdOrderIngestRowOut(BaseModel):
    order_id: str
    jd_order_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class JdOrderIngestDataOut(BaseModel):
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
    rows: List[JdOrderIngestRowOut]


class JdOrderIngestEnvelopeOut(BaseModel):
    ok: bool
    data: JdOrderIngestDataOut
