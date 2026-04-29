from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.oms.order_facts.contracts.collector_import import (
    ImportPlatformOrderMirrorFromCollectorIn,
    ImportPlatformOrderMirrorFromCollectorOut,
    SyncPlatformOrderMirrorsFromCollectorIn,
    SyncPlatformOrderMirrorsFromCollectorOut,
)
from app.oms.order_facts.contracts.platform_order_mirror import (
    PlatformOrderMirrorEnvelopeOut,
    PlatformOrderMirrorImportIn,
    PlatformOrderMirrorListOut,
)
from app.oms.order_facts.services.collector_export_client import (
    CollectorExportError,
    CollectorExportNotFound,
    CollectorExportUpstreamError,
)
from app.oms.order_facts.services.collector_import_service import (
    import_platform_order_mirror_from_collector,
    sync_platform_order_mirrors_from_collector,
)
from app.oms.order_facts.services.platform_order_mirror_service import (
    get_platform_order_mirror_detail,
    list_platform_order_mirrors,
    upsert_platform_order_mirror,
)


router = APIRouter(tags=["oms-platform-order-mirrors"])


def _route_name(platform: str, suffix: str) -> str:
    return f"{platform}_{suffix}"


def _register_platform_routes(platform: str) -> None:
    @router.post(
        f"/{platform}/platform-order-mirrors/import",
        response_model=PlatformOrderMirrorEnvelopeOut,
        name=_route_name(platform, "import_platform_order_mirror"),
    )
    async def import_platform_order_mirror(
        payload: PlatformOrderMirrorImportIn = Body(...),
        session: AsyncSession = Depends(get_async_session),
    ) -> PlatformOrderMirrorEnvelopeOut:
        try:
            data = await upsert_platform_order_mirror(
                session,
                platform=platform,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return PlatformOrderMirrorEnvelopeOut(ok=True, data=data)

    @router.post(
        f"/{platform}/platform-order-mirrors/import-from-collector",
        response_model=ImportPlatformOrderMirrorFromCollectorOut,
        name=_route_name(platform, "import_platform_order_mirror_from_collector_route"),
    )
    async def import_platform_order_mirror_from_collector_route(
        payload: ImportPlatformOrderMirrorFromCollectorIn = Body(...),
        session: AsyncSession = Depends(get_async_session),
    ) -> ImportPlatformOrderMirrorFromCollectorOut:
        try:
            data = await import_platform_order_mirror_from_collector(
                session,
                platform=platform,
                collector_order_id=payload.collector_order_id,
            )
        except CollectorExportNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CollectorExportUpstreamError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except CollectorExportError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return ImportPlatformOrderMirrorFromCollectorOut(
            ok=True,
            imported=True,
            platform=platform,
            collector_order_id=int(payload.collector_order_id),
            mirror_id=int(data.id),
        )

    @router.post(
        f"/{platform}/platform-order-mirrors/sync-from-collector",
        response_model=SyncPlatformOrderMirrorsFromCollectorOut,
        name=_route_name(platform, "sync_platform_order_mirrors_from_collector_route"),
    )
    async def sync_platform_order_mirrors_from_collector_route(
        payload: SyncPlatformOrderMirrorsFromCollectorIn = Body(...),
        session: AsyncSession = Depends(get_async_session),
    ) -> SyncPlatformOrderMirrorsFromCollectorOut:
        try:
            return await sync_platform_order_mirrors_from_collector(
                session,
                platform=platform,
                limit=payload.limit,
                offset=payload.offset,
                since=payload.since,
                until=payload.until,
            )
        except CollectorExportUpstreamError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except CollectorExportError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        f"/{platform}/platform-order-mirrors",
        response_model=PlatformOrderMirrorListOut,
        name=_route_name(platform, "list_platform_order_mirror_rows"),
    )
    async def list_platform_order_mirror_rows(
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_async_session),
    ) -> PlatformOrderMirrorListOut:
        rows = await list_platform_order_mirrors(
            session,
            platform=platform,
            limit=limit,
            offset=offset,
        )
        return PlatformOrderMirrorListOut(ok=True, data=rows)

    @router.get(
        f"/{platform}/platform-order-mirrors/{{mirror_id}}",
        response_model=PlatformOrderMirrorEnvelopeOut,
        name=_route_name(platform, "get_platform_order_mirror_row"),
    )
    async def get_platform_order_mirror_row(
        mirror_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_async_session),
    ) -> PlatformOrderMirrorEnvelopeOut:
        data = await get_platform_order_mirror_detail(
            session,
            platform=platform,
            mirror_id=mirror_id,
        )
        if data is None:
            raise HTTPException(status_code=404, detail=f"{platform} platform order mirror not found")
        return PlatformOrderMirrorEnvelopeOut(ok=True, data=data)


for _platform in ("pdd", "taobao", "jd"):
    _register_platform_routes(_platform)
