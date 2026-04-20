from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class OutboundLotCandidateOut(_Base):
    lot_id: Annotated[int, Field(ge=1)]
    lot_code: str | None = None
    production_date: date | None = None
    expiry_date: date | None = None
    available_qty: Annotated[int, Field(ge=0)]


class OutboundLotCandidatesOut(_Base):
    warehouse_id: Annotated[int, Field(ge=1)]
    item_id: Annotated[int, Field(ge=1)]
    candidates: list[OutboundLotCandidateOut] = Field(default_factory=list)


__all__ = [
    "OutboundLotCandidateOut",
    "OutboundLotCandidatesOut",
]
