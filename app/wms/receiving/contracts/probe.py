from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundTaskProbeStatus(str, Enum):
    MATCHED = "MATCHED"
    UNBOUND = "UNBOUND"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"


class InboundTaskProbeIn(_Base):
    barcode: Annotated[str, Field(min_length=1, max_length=128, description="原始扫码内容")]

    @field_validator("barcode", mode="before")
    @classmethod
    def _trim_barcode(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class InboundTaskProbeOut(_Base):
    ok: bool
    status: InboundTaskProbeStatus
    barcode: str

    item_id: int | None = None
    item_uom_id: int | None = None
    ratio_to_base: int | None = None

    matched_line_no: int | None = None
    item_name_snapshot: str | None = None
    uom_name_snapshot: str | None = None

    message: str | None = None


__all__ = [
    "InboundTaskProbeIn",
    "InboundTaskProbeOut",
    "InboundTaskProbeStatus",
]
