# app/schemas/outbound.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OutboundLine(BaseModel):
    item_id: int = Field(..., description="SKU/Item 标识", gt=0)
    warehouse_id: int = Field(..., description="仓库 ID（>0）", gt=0)
    qty: int = Field(..., gt=0, description="本行出库数量（>0）")

    batch_code: Optional[str] = Field(default=None, description="Lot 展示码（批次码；NONE 商品必须为 null）")

    @field_validator("item_id", "warehouse_id")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be > 0")
        return v


class OutboundCommitRequest(BaseModel):
    platform: str
    shop_id: Optional[str] = None
    ref: str
    occurred_at: datetime

    warehouse_id: Optional[int] = None
    lines: List[OutboundLine]

    @field_validator("occurred_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class OutboundResultLine(BaseModel):
    item_id: int
    warehouse_id: int
    batch_code: Optional[str] = None
    qty: int
    status: str  # "OK" / "INSUFFICIENT" / "REJECTED" / "IDEMPOTENT"


class OutboundCommitSummary(BaseModel):
    total_lines: int
    total_qty: int


class OutboundCommitMeta(BaseModel):
    ref: str
    store_id: Optional[int] = None
    warehouse_id: Optional[int] = None


class OutboundCommitResponse(BaseModel):
    ok: bool
    summary: OutboundCommitSummary
    meta: OutboundCommitMeta
    results: List[OutboundResultLine]

    @classmethod
    def from_service_payload(cls, payload: Dict[str, Any]) -> "OutboundCommitResponse":
        meta = payload.get("meta", {}) or {}
        summary = payload.get("summary", {}) or {}
        return cls(
            ok=bool(payload.get("ok", True)),
            summary=OutboundCommitSummary(
                total_lines=int(summary.get("total_lines", 0)),
                total_qty=int(summary.get("total_qty", 0)),
            ),
            meta=OutboundCommitMeta(
                ref=str(meta.get("ref", "")),
                store_id=meta.get("store_id"),
                warehouse_id=meta.get("warehouse_id"),
            ),
            results=[OutboundResultLine(**r) for r in payload.get("results", [])],
        )
