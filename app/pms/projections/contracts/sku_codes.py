# app/pms/projections/contracts/sku_codes.py
from __future__ import annotations

from typing import Literal

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionCheckOut,
    PmsProjectionListOut,
    PmsProjectionSyncOut,
)


class PmsSkuCodesProjectionListOut(PmsProjectionListOut):
    resource: Literal["sku-codes"]


class PmsSkuCodesProjectionCheckOut(PmsProjectionCheckOut):
    resource: Literal["sku-codes"]


class PmsSkuCodesProjectionSyncOut(PmsProjectionSyncOut):
    pass


__all__ = [
    "PmsSkuCodesProjectionCheckOut",
    "PmsSkuCodesProjectionListOut",
    "PmsSkuCodesProjectionSyncOut",
]
