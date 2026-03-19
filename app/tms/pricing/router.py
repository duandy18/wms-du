from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

from .contracts import PricingListResponse
from .repository import list_pricing_view
from .routes_bindings import router as bindings_router

router = APIRouter(prefix="/tms/pricing", tags=["tms-pricing"])


@router.get("/list", response_model=PricingListResponse, name="pricing_list_view")
async def get_pricing_list(
    session: AsyncSession = Depends(get_session),
) -> PricingListResponse:
    rows = await list_pricing_view(session)
    return PricingListResponse(rows=rows)


router.include_router(bindings_router)
