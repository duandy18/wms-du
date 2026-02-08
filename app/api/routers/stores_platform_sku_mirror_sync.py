# app/api/routers/stores_platform_sku_mirror_sync.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.pdd import PddAdapter
from app.api.deps import get_current_user
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.platform_sku_mirror_sync import PlatformSkuMirrorSyncIn, PlatformSkuMirrorSyncOut
from app.db.deps import get_db
from app.services.platform_sku_mirror_service import PlatformSkuMirrorService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_dt(v: Any) -> datetime | None:
    return v if isinstance(v, datetime) else None


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/stores")  # tags 由 stores 顶层 router 统一提供

    @r.post("/{store_id}/platform-skus/sync-mirror", response_model=PlatformSkuMirrorSyncOut)
    async def sync_mirror(
        store_id: int,
        payload: PlatformSkuMirrorSyncIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> PlatformSkuMirrorSyncOut:
        check_perm(db, current_user, ["config.store.write"])

        platform = payload.platform.strip().lower()
        if platform != "pdd":
            raise HTTPException(status_code=400, detail=f"platform not supported yet: {payload.platform}")

        adapter = PddAdapter()
        mirrors = await adapter.fetch_sku_mirrors(store_id=store_id, platform_sku_ids=payload.platform_sku_ids)

        svc = PlatformSkuMirrorService(db)
        now = _utc_now()

        upserted = 0
        for it in mirrors:
            pid = str(it.get("platform_sku_id") or "").strip()
            if not pid:
                continue

            observed_at = _as_dt(it.get("observed_at")) or now
            source = str(it.get("source") or payload.source)

            svc.upsert(
                platform=platform,
                shop_id=store_id,
                platform_sku_id=pid,
                sku_name=it.get("sku_name"),
                spec=it.get("spec"),
                raw_payload=it.get("raw_payload"),
                source=source,
                observed_at=observed_at,
            )
            upserted += 1

        db.commit()
        return PlatformSkuMirrorSyncOut(ok=True, fetched=len(mirrors), upserted=upserted)

    router.include_router(r)
