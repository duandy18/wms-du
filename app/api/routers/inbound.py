# app/api/routers/inbound.py
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_by_sku, fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.deps import get_session
from app.services.inbound_service import InboundService

UTC = timezone.utc

router = APIRouter(prefix="/inbound")


class ReceiveIn(BaseModel):
    # 二选一：item_id 或 sku
    item_id: Optional[int] = None
    sku: Optional[str] = None

    # 核心参数
    qty: int
    ref: str
    ref_line: int | str = 1  # 允许传 "L1"、"1" 或直接 int

    # 粒度与批次（可缺省，服务层有兜底）
    warehouse_id: Optional[int] = None
    batch_code: Optional[str] = None

    # 日期（至少其一；若都缺省，服务层会以 production_date=today 兜底）
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    @field_validator("ref_line", mode="before")
    @classmethod
    def _coerce_ref_line(cls, v: Any) -> int:
        """
        兼容把 ref_line 作为字符串传入的老用例：
        - "L1" → 1；"001" → 1；无法解析 → 1
        """
        if v is None:
            return 1
        if isinstance(v, int):
            return v if v > 0 else 1
        s = str(v).strip()
        m = re.search(r"\d+", s)
        return int(m.group(0)) if m else 1


@router.post("/receive")
async def receive(
    payload: ReceiveIn,
    session: AsyncSession = Depends(get_session),
):
    """
    入库入口（v2）：接受 JSON 请求体。
    - 支持以 sku 或 item_id 指定商品；
    - 其他缺省值（warehouse_id/batch_code/日期）由 InboundService 兜底；
    - 幂等由 StockService.adjust 命中唯一键保障。
    """
    try:
        # ✅ 主线 A：API 合同收紧（422 拦假码）
        item_id: Optional[int] = payload.item_id
        requires_batch: Optional[bool] = None

        if item_id is not None:
            has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(item_id)})
            if item_id not in has_shelf_life_map:
                raise HTTPException(status_code=422, detail=f"unknown item_id: {item_id}")
            requires_batch = has_shelf_life_map.get(item_id, False) is True
        else:
            if not payload.sku or not payload.sku.strip():
                raise HTTPException(status_code=422, detail="either item_id or sku is required.")
            found = await fetch_item_by_sku(session, payload.sku)
            if not found:
                raise HTTPException(status_code=422, detail=f"unknown sku: {payload.sku.strip()}")
            item_id, requires_batch = found[0], found[1]

        batch_code = validate_batch_code_contract(requires_batch=requires_batch is True, batch_code=payload.batch_code)

        svc = InboundService()
        result = await svc.receive(
            session=session,
            item_id=item_id,
            sku=payload.sku,
            qty=payload.qty,
            ref=payload.ref,
            ref_line=int(payload.ref_line),  # 已通过校验器规范化
            occurred_at=datetime.now(UTC),
            warehouse_id=payload.warehouse_id,
            batch_code=batch_code,
            production_date=payload.production_date,
            expiry_date=payload.expiry_date,
        )
        return {"status": "OK", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
