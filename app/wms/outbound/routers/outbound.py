# app/wms/outbound/routers/outbound.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, constr
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.db.deps import get_async_session as get_session
from app.core.audit import new_trace
from app.wms.outbound.services.outbound_commit_service import OutboundService

router = APIRouter(prefix="/outbound", tags=["outbound"])

PlatformStr = constr(min_length=1, max_length=32)


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


class OutboundLineIn(BaseModel):
    """出库行：按 (warehouse_id, item_id, batch_code) 粒度扣减。"""

    warehouse_id: int
    item_id: int

    # ✅ 合同双轨：lot_code 正名 + batch_code 兼容
    lot_code: Optional[str] = Field(default=None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = None

    qty: int = Field(gt=0)


class OutboundShipIn(BaseModel):
    """
    出库请求体（v2+v3 统一版）：

      - platform / shop_id / ref：业务键，用于生成幂等用的 order_id
      - external_order_ref：可选，挂渠道订单号（当前仅透传给审计/上层，不影响扣减）
      - occurred_at：可选，不传则用当前时间
      - lines：一组出库行
    """

    platform: PlatformStr
    shop_id: constr(min_length=1)
    ref: constr(min_length=1)

    external_order_ref: Optional[str] = None
    occurred_at: Optional[datetime] = None
    lines: List[OutboundLineIn]


class OutboundShipOut(BaseModel):
    status: str
    total_qty: int
    trace_id: str
    idempotent: bool = False


@router.post("/ship/commit", response_model=OutboundShipOut)
async def outbound_ship_commit(
    payload: OutboundShipIn,
    session: AsyncSession = Depends(get_session),
):
    """
    出库入口（统一版，真正扣库存）：

    - 每次调用都会生成一个 trace_id，用于串联订单 / 预占 / 出库 / ledger；
    - 实际库存扣减与台账写入统一走 OutboundService → StockService.adjust；
    - 幂等：以 (platform, shop_id, ref) 组成的 order_id 作为业务键，
      OutboundService 会通过 stock_ledger 中已有 delta 判断“已扣数量”，
      只扣“剩余需要扣”的部分；若 total_qty=0，则视为完全幂等。

    Phase M：
    - 策略真相源：items.expiry_policy（NONE/REQUIRED）
    - requires_batch 由 expiry_policy 投影

    Phase M-4 governance：
    - lot_code 正名；batch_code 兼容别名（内部仍沿用 batch_code key）
    """
    trace = new_trace("http:/outbound/ship/commit")

    # ✅ 主线 A：API 合同收紧（422 拦假码）
    item_ids: Set[int] = {ln.item_id for ln in payload.lines}
    expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)

    missing_items = [str(i) for i in sorted(item_ids) if i not in expiry_policy_map]
    if missing_items:
        raise HTTPException(status_code=422, detail=f"unknown item_id(s): {', '.join(missing_items)}")

    normalized_lines = []
    for ln in payload.lines:
        pol = expiry_policy_map.get(ln.item_id, "NONE")
        requires_batch = _requires_batch_from_expiry_policy(pol)

        lot_code = ln.lot_code or ln.batch_code
        norm_batch = validate_lot_code_contract(requires_batch=requires_batch, lot_code=lot_code)

        normalized_lines.append(
            {
                "warehouse_id": ln.warehouse_id,
                "item_id": ln.item_id,
                "batch_code": norm_batch,  # 兼容：内部仍使用 batch_code 字段名
                "qty": ln.qty,
            }
        )

    svc = OutboundService()

    # 业务幂等键：platform + shop_id + ref
    order_id = f"{payload.platform.upper()}:{payload.shop_id}:{payload.ref}"

    result = await svc.commit(
        session=session,
        order_id=order_id,
        lines=normalized_lines,
        occurred_at=payload.occurred_at,
        trace_id=trace.trace_id,
    )

    await session.commit()

    total_qty = int(result.get("total_qty", 0))
    idempotent = total_qty == 0

    return OutboundShipOut(
        status=result.get("status", "OK"),
        total_qty=total_qty,
        trace_id=trace.trace_id,
        idempotent=idempotent,
    )
