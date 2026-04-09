# app/pms/public/items/contracts/barcode_probe.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.pms.public.items.contracts.item_basic import ItemBasic


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
    )


class BarcodeProbeStatus(str, Enum):
    BOUND = "BOUND"
    UNBOUND = "UNBOUND"
    ERROR = "ERROR"


class BarcodeProbeIn(_Base):
    barcode: str = Field(..., min_length=1, max_length=128)

    @field_validator("barcode", mode="before")
    @classmethod
    def _trim_barcode(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


class BarcodeProbeError(_Base):
    stage: str
    error: str


class BarcodeProbeOut(_Base):
    ok: bool
    status: BarcodeProbeStatus
    barcode: str

    item_id: int | None = None
    item_uom_id: int | None = None
    ratio_to_base: int | None = None

    symbology: str | None = None
    active: bool | None = None

    item_basic: ItemBasic | None = None

    errors: list[BarcodeProbeError] = Field(default_factory=list)
