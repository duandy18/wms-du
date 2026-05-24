# app/pms/projections/contracts/items.py
from __future__ import annotations

from typing import Literal

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionCheckOut,
    PmsProjectionListOut,
    PmsProjectionSyncOut,
)


class PmsItemsProjectionListOut(PmsProjectionListOut):
    resource: Literal["items"]


class PmsItemsProjectionCheckOut(PmsProjectionCheckOut):
    resource: Literal["items"]


class PmsItemsProjectionSyncOut(PmsProjectionSyncOut):
    pass


__all__ = [
    "PmsItemsProjectionCheckOut",
    "PmsItemsProjectionListOut",
    "PmsItemsProjectionSyncOut",
]
