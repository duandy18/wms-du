# app/services/scan_handlers/count_handler.py
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item


async def handle_count(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    actual: int,
    ref: str,
    production_date: date | None = None,
    expiry_date: date | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    盘点（Count）—— v2：按 仓库 + 商品 + 批次 粒度。

    规则：
    - actual >= 0
    - 盘盈（delta > 0）属于“隐式入库”，必须有 production_date 或 expiry_date（至少其一）；
      若仅有 production_date 且 Item 配置了保质期，则自动推算 expiry_date。
    - 盘亏（delta < 0）只做扣减，不强制日期。
    """
    if actual < 0:
        raise ValueError("Actual quantity must be non-negative.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("盘点操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("盘点操作必须明确 warehouse_id。")

    # 当前库存（按 warehouse + item + batch 粒度加锁读取）
    row = await session.execute(
        sa.text(
            "SELECT qty FROM stocks "
            "WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c "
            "FOR UPDATE"
        ),
        {"i": item_id, "w": warehouse_id, "c": str(batch_code).strip()},
    )
    current = int(row.scalar_one_or_none() or 0)
    delta = int(actual) - current
    before = current
    after = current + delta

    # 只有盘盈需要按“入库”逻辑补齐日期
    if delta > 0:
        if production_date is None and expiry_date is None:
            raise ValueError("盘盈为入库行为，必须提供 production_date 或 expiry_date。")

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    if delta != 0:
        await StockService().adjust(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            delta=delta,
            reason=MovementType.COUNT,
            ref=ref,
            batch_code=str(batch_code).strip(),
            production_date=production_date,
            expiry_date=expiry_date,
            trace_id=trace_id,
        )

    # 统一返回 enriched payload，方便 orchestrator 直接挂到 ScanResponse
    return {
        "item_id": int(item_id),
        "warehouse_id": int(warehouse_id),
        "batch_code": str(batch_code),
        "actual": int(actual),
        "delta": int(delta),
        "before": int(before),
        "after": int(after),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
