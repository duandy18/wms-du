from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session

from .bindings.routes import router as bindings_router
from .summary.contracts import PricingListResponse
from .summary.repository import list_pricing_view
from .templates.router import router as templates_router

router = APIRouter(prefix="/shipping-assist/pricing", tags=["shipping-assist-pricing"])


@router.get("/list", response_model=PricingListResponse, name="pricing_list_view")
async def get_pricing_list(
    session: AsyncSession = Depends(get_session),
) -> PricingListResponse:
    rows = await list_pricing_view(session)
    return PricingListResponse(rows=rows)


router.include_router(bindings_router)
router.include_router(templates_router)
