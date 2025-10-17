from typing import Literal

from pydantic import BaseModel, Field


class OutboundLine(BaseModel):
    item_id: int
    location_id: int
    qty: int = Field(gt=0)


class OutboundCommitRequest(BaseModel):
    ref: str = Field(min_length=1, max_length=64)
    lines: list[OutboundLine]


class OutboundCommitResultLine(BaseModel):
    item_id: int
    location_id: int
    committed_qty: int
    status: Literal["OK", "IDEMPOTENT", "INSUFFICIENT_STOCK"]


class OutboundCommitResponse(BaseModel):
    ref: str
    results: list[OutboundCommitResultLine]
