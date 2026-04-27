from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.oms.platforms.pdd.contracts_fact_bridge import (
    PddFactBridgeDataOut,
    PddFactBridgeEnvelopeOut,
)
from app.oms.platforms.pdd.service_fact_bridge import (
    PddFactBridgeService,
    PddFactBridgeServiceError,
)

router = APIRouter(tags=["oms-pdd-fact-bridge"])


@router.post(
    "/pdd/orders/{pdd_order_id}/facts/bridge",
    response_model=PddFactBridgeEnvelopeOut,
    summary="PDD 专表事实桥接为 OMS 归一订单事实行",
)
async def bridge_pdd_order_to_platform_facts(
    pdd_order_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
) -> PddFactBridgeEnvelopeOut:
    """
    只桥接事实行，不做 FSKU 解析、内部建单或财务计算。
    """

    try:
        result = await PddFactBridgeService().bridge_one_order(
            session,
            pdd_order_id=int(pdd_order_id),
        )
        await session.commit()
    except (ValueError, LookupError, PddFactBridgeServiceError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to bridge pdd order facts: {exc}",
        ) from exc

    return PddFactBridgeEnvelopeOut(
        ok=True,
        data=PddFactBridgeDataOut(
            platform=result.platform,
            store_id=result.store_id,
            store_code=result.store_code,
            pdd_order_id=result.pdd_order_id,
            ext_order_no=result.ext_order_no,
            lines_count=result.lines_count,
            facts_written=result.facts_written,
        ),
    )
