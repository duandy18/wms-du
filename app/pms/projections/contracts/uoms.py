# app/pms/projections/contracts/uoms.py
from __future__ import annotations

from typing import Literal

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionCheckOut,
    PmsProjectionListOut,
    PmsProjectionSyncOut,
)


class PmsUomsProjectionListOut(PmsProjectionListOut):
    resource: Literal["uoms"]


class PmsUomsProjectionCheckOut(PmsProjectionCheckOut):
    resource: Literal["uoms"]


class PmsUomsProjectionSyncOut(PmsProjectionSyncOut):
    pass


__all__ = [
    "PmsUomsProjectionCheckOut",
    "PmsUomsProjectionListOut",
    "PmsUomsProjectionSyncOut",
]
