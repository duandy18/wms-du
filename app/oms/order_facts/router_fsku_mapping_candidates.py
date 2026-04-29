from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.oms.order_facts.contracts.fsku_mapping_candidate import (
    FskuMappingCandidateListOut,
)
from app.oms.order_facts.services.fsku_mapping_candidate_service import (
    list_fsku_mapping_candidates,
)


router = APIRouter(tags=["oms-fsku-mapping-candidates"])


def _route_name(platform: str, suffix: str) -> str:
    return f"{platform}_{suffix}"


def _register_platform_routes(platform: str) -> None:
    @router.get(
        f"/{platform}/fsku-mapping/candidates",
        response_model=FskuMappingCandidateListOut,
        name=_route_name(platform, "list_platform_fsku_mapping_candidates"),
    )
    async def list_platform_fsku_mapping_candidates(
        store_code: str | None = Query(None, min_length=1, max_length=128),
        merchant_code: str | None = Query(None, min_length=1, max_length=128),
        only_unbound: bool = Query(False),
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_async_session),
    ) -> FskuMappingCandidateListOut:
        try:
            data = await list_fsku_mapping_candidates(
                session,
                platform=platform,
                store_code=store_code,
                merchant_code=merchant_code,
                only_unbound=only_unbound,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return FskuMappingCandidateListOut(ok=True, data=data)


for _platform in ("pdd", "taobao", "jd"):
    _register_platform_routes(_platform)
