# app/wms/system/read_v1/routers/iam_snapshot.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.read_v1.contracts import WmsSystemIamSnapshotOut
from app.wms.system.read_v1.repos import WmsIamSnapshotRepo
from app.wms.system.read_v1.services import WmsIamSnapshotService
from app.wms.system.service_auth.deps import require_wms_service_capability

router = APIRouter(prefix="/system/read/v1", tags=["system-read-v1"])

require_wms_read_iam_snapshot = require_wms_service_capability(
    "wms.read.iam_snapshot",
)


@router.get(
    "/iam-snapshot",
    response_model=WmsSystemIamSnapshotOut,
    summary="Get WMS IAM snapshot",
)
async def get_wms_iam_snapshot(
    _service_permission: None = Depends(require_wms_read_iam_snapshot),
    db: Session = Depends(get_db),
) -> WmsSystemIamSnapshotOut:
    """
    Return WMS users, user permissions, and page permission catalog for ERP projection sync.

    Boundary:
    - Only ERP service client should be granted this capability.
    - This endpoint is read-only.
    - This endpoint never exposes password_hash, tokens, or secrets.
    - This endpoint does not write WMS permissions.
    - This endpoint does not migrate permission execution to ERP.
    """

    return WmsIamSnapshotService(WmsIamSnapshotRepo(db)).get_iam_snapshot()


__all__ = ["router"]
