from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.wms.inventory_adjustment.count.contracts.count import CountRequest, CountResponse
from app.wms.inventory_adjustment.count.services.count_service import CountService

router = APIRouter(prefix="/count", tags=["count"])


@router.post("", response_model=CountResponse, status_code=status.HTTP_200_OK)
async def count_inventory(
    req: CountRequest,
    session: AsyncSession = Depends(get_async_session),
) -> CountResponse:
    service = CountService()
    try:
        return await service.submit(session, req=req)
    except LookupError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"count failed: {e}") from e
