# app/wms/system/read_v1/routers/page_catalog.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.read_v1.contracts import WmsSystemPageCatalogOut
from app.wms.system.read_v1.repos import WmsPageCatalogRepo
from app.wms.system.read_v1.services import WmsPageCatalogService

router = APIRouter(prefix="/system/read/v1", tags=["system-read-v1"])


@router.get(
    "/page-catalog",
    response_model=WmsSystemPageCatalogOut,
    summary="Get WMS page catalog",
)
async def get_wms_page_catalog(
    db: Session = Depends(get_db),
) -> WmsSystemPageCatalogOut:
    """
    Return WMS page catalog for ERP page projection sync.

    Boundary:
    - This endpoint is read-only.
    - ERP must not connect to WMS DB directly.
    - ERP must not infer WMS pages from frontend routes.
    """

    return WmsPageCatalogService(WmsPageCatalogRepo(db)).get_page_catalog()


__all__ = ["router"]
