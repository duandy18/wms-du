# app/wms/stock/services/stock_contract_resolver.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.lot_code_contract import validate_lot_code_contract
from app.wms.stock.services.lot_resolver import LotResolver


async def resolve_lot_for_stock_adjust(
    session: AsyncSession,
    *,
    lot_resolver: LotResolver,
    item_id: int,
    warehouse_id: int,
    batch_code: Optional[str],
    lot_id: Optional[int],
    ref: str,
    occurred_at: Optional[datetime],
) -> Tuple[int, Optional[str]]:
    """
    任务3（StockService API 拆分）第一刀：抽离“合同裁决 + lot_id 解析”。

    约束：
    - 本模块只负责：
        1) requires_batch（items.expiry_policy 投影）
        2) validate_lot_code_contract（REQUIRED/NONE 合同裁决）
        3) ensure_*_lot_id（lot identity 解析 / 创建入口）
    - 不负责写库存（不得调用 adjust_lot_impl），以保持“执行器单入口”铁律。
    """
    requires_batch = await lot_resolver.requires_batch(session, item_id=int(item_id))
    bc_norm = validate_lot_code_contract(requires_batch=requires_batch, lot_code=batch_code)

    if bc_norm is None:
        resolved_lot_id = lot_id or await lot_resolver.ensure_internal_lot_id(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            ref=str(ref),
            occurred_at=occurred_at,
        )
    else:
        resolved_lot_id = lot_id or await lot_resolver.ensure_supplier_lot_id(
            session,
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
            lot_code=bc_norm,
            occurred_at=occurred_at,
        )

    return int(resolved_lot_id), bc_norm
