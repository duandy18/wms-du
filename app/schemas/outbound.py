# app/schemas/outbound.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OutboundMode(str, Enum):
    FEFO = "FEFO"
    NORMAL = "NORMAL"


class OutboundLine(BaseModel):
    item_id: int = Field(..., description="SKU/Item 标识")
    location_id: int = Field(..., gt=0, description="库位 ID（>0）")
    qty: int = Field(..., gt=0, description="本行出库数量（>0）")

    @field_validator("item_id")
    @classmethod
    def _item_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("item_id must be > 0")
        return v


class OutboundCommitRequest(BaseModel):
    platform: str
    shop_id: Optional[str] = None
    ref: str
    occurred_at: datetime
    warehouse_id: Optional[int] = None
    mode: OutboundMode = OutboundMode.FEFO
    allow_expired: bool = False
    lines: List[OutboundLine]

    @field_validator("occurred_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class OutboundResultLine(BaseModel):
    item_id: int
    location_id: int
    qty: int
    status: str  # "OK" / "IDEMPOTENT" / "IGNORED"


class OutboundCommitSummary(BaseModel):
    total_lines: int
    total_qty: int


class OutboundCommitMeta(BaseModel):
    ref: str
    store_id: Optional[int] = None
    warehouse_id: Optional[int] = None


class OutboundCommitResponse(BaseModel):
    ok: bool
    mode: OutboundMode
    summary: OutboundCommitSummary
    meta: OutboundCommitMeta
    results: List[OutboundResultLine]

    @classmethod
    def from_service_payload(cls, payload: Dict[str, Any]) -> "OutboundCommitResponse":
        meta = payload.get("meta", {}) or {}
        summary = payload.get("summary", {}) or {}
        return cls(
            ok=bool(payload.get("ok", True)),
            mode=OutboundMode(payload.get("mode", "FEFO")),
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
