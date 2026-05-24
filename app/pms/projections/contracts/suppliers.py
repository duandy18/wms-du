# app/pms/projections/contracts/suppliers.py
from __future__ import annotations

from typing import Literal

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionCheckOut,
    PmsProjectionListOut,
    PmsProjectionSyncOut,
)


class PmsSuppliersProjectionListOut(PmsProjectionListOut):
    resource: Literal["suppliers"]


class PmsSuppliersProjectionCheckOut(PmsProjectionCheckOut):
    resource: Literal["suppliers"]


class PmsSuppliersProjectionSyncOut(PmsProjectionSyncOut):
    pass


__all__ = [
    "PmsSuppliersProjectionCheckOut",
    "PmsSuppliersProjectionListOut",
    "PmsSuppliersProjectionSyncOut",
]
