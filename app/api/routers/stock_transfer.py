# app/api/routers/stock_transfer.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.stock import StockTransferIn, StockTransferMove, StockTransferOut
from app.services.inventory_ops import InventoryOpsService

router = APIRouter(prefix="/stock/transfer", tags=["stock"])


@router.post("", response_model=StockTransferOut)
async def transfer_stock(
    body: StockTransferIn,
    session: AsyncSession = Depends(get_session),
) -> StockTransferOut:
    """
    库内搬运（同仓 from→to）：
    - 调用 InventoryOpsService.transfer(session, item_id, from_location_id, to_location_id, qty, reason, ref)
    - 成功返回 total_moved；批次明细 moves 先保持最小实现（空列表），后续可扩展
    """
    svc = InventoryOpsService()
    try:
        res = await svc.transfer(
            session=session,
            item_id=body.item_id,
            from_location_id=body.src_location_id,
            to_location_id=body.dst_location_id,
            qty=body.qty,
            reason=(body.reason or "MOVE"),
            ref=body.ref,
        )
        await session.commit()
    except ValueError as e:
        # 业务冲突：库存不足、跨仓禁止、库位不存在等
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except AssertionError as e:
        # 入参断言不满足（qty<=0 等）
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    # InventoryOpsService.transfer 返回: {"ok": True, "idempotent": bool, "moved": int}
    return StockTransferOut(
        item_id=body.item_id,
        src_location_id=body.src_location_id,
        dst_location_id=body.dst_location_id,
        total_moved=int(res.get("moved", 0)),
        # 如需批次维度明细，可在 service 返回结构中增加 batch_moves 并在此转换
        moves=[],  # [StockTransferMove(...), ...]
    )
