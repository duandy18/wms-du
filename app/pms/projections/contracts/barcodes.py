# app/pms/projections/contracts/barcodes.py
from __future__ import annotations

from typing import Literal

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionCheckOut,
    PmsProjectionListOut,
    PmsProjectionSyncOut,
)


class PmsBarcodesProjectionListOut(PmsProjectionListOut):
    resource: Literal["barcodes"]


class PmsBarcodesProjectionCheckOut(PmsProjectionCheckOut):
    resource: Literal["barcodes"]


class PmsBarcodesProjectionSyncOut(PmsProjectionSyncOut):
    pass


__all__ = [
    "PmsBarcodesProjectionCheckOut",
    "PmsBarcodesProjectionListOut",
    "PmsBarcodesProjectionSyncOut",
]
