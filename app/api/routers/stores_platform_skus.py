from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.platform_sku_list import PlatformSkuListOut
from app.db.deps import get_db
from app.services.platform_sku_query_service import PlatformSkuQueryService

router = APIRouter(prefix="/stores", tags=["ops - stores"])


def _svc(db: Session = Depends(get_db)) -> PlatformSkuQueryService:
    return PlatformSkuQueryService(db)


@router.get("/{store_id}/platform-skus", response_model=PlatformSkuListOut)
def list_platform_skus(
    store_id: int,
    with_binding: int = Query(1, ge=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
    current_user=Depends(get_current_user),
    svc: PlatformSkuQueryService = Depends(_svc),
) -> PlatformSkuListOut:
    check_perm(svc.db, current_user, ["config.store.write"])

    return svc.list_by_store(
        store_id=store_id,
        with_binding=bool(with_binding),
        limit=limit,
        offset=offset,
        q=q,
    )
