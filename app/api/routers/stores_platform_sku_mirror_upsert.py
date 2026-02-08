# app/api/routers/stores_platform_sku_mirror_upsert.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.platform_sku_mirror_sync import (
    PlatformSkuMirrorUpsertIn,
    PlatformSkuMirrorUpsertOut,
)
from app.db.deps import get_db
from app.services.platform_sku_mirror_service import PlatformSkuMirrorService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/stores", tags=["stores"])

    @r.post("/{store_id}/platform-skus/mirror-upsert", response_model=PlatformSkuMirrorUpsertOut)
    def mirror_upsert(
        store_id: int,
        payload: PlatformSkuMirrorUpsertIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> PlatformSkuMirrorUpsertOut:
        check_perm(db, current_user, ["config.store.write"])

        svc = PlatformSkuMirrorService(db)

        now = _utc_now()
        n = 0
        for it in payload.items:
            svc.upsert(
                platform=payload.platform,
                shop_id=store_id,
                platform_sku_id=it.platform_sku_id,
                sku_name=it.sku_name,
                spec=it.spec,
                raw_payload=it.raw_payload,
                source=payload.source,
                observed_at=it.observed_at or now,
            )
            n += 1

        db.commit()
        return PlatformSkuMirrorUpsertOut(ok=True, upserted=n)

    router.include_router(r)
