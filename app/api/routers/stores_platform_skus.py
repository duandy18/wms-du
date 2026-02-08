# app/api/routers/stores_platform_skus.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.schemas.platform_sku_list import PlatformSkuListOut
from app.db.deps import get_db
from app.services.platform_sku_query_service import PlatformSkuQueryService


def register(router: APIRouter) -> None:
    # ✅ tags 由顶层 stores router 统一提供；子模块不重复声明，避免 ['stores','stores']
    r = APIRouter(prefix="/stores")

    @r.get("/{store_id}/platform-skus", response_model=PlatformSkuListOut)
    def list_platform_skus(
        store_id: int,
        with_binding: int = Query(1, ge=0, le=1),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        q: str | None = Query(None),
        db: Session = Depends(get_db),
    ) -> PlatformSkuListOut:
        svc = PlatformSkuQueryService(db)
        return svc.list_by_store(
            store_id=store_id,
            with_binding=bool(with_binding),
            limit=limit,
            offset=offset,
            q=q,
        )

    router.include_router(r)
