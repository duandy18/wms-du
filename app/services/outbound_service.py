# app/services/outbound_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.store import Store
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.store_service import StoreService


class OutboundService:
    @staticmethod
    async def commit(
        session: AsyncSession,
        *,
        platform: str = "pdd",
        shop_id: str,
        ref: str,
        lines: List[Dict],
        refresh_visible: bool = True,
        warehouse_id: int | None = None,  # 预留：多仓阶段启用；v1.0 单仓忽略
    ) -> Dict[str, Any]:
        """
        出库（幂等 + 台账兜底）：
          1) 业务幂等：outbound_ship_ops (UQ: store_id, ref, item_id, location_id)
          2) 台账兜底幂等：reason/ref/ref_line/stock_id 存在则跳过
          3) 扣减 stocks.qty → 写 stock_ledger(UTC aware) → -reserved → 可选刷新 visible
        返回：
          {"store_id": <int|None>, "ref": <str>, "results": [
              {"item_id": int, "location_id": int, "qty": int, "status": "OK|IDEMPOTENT|NO_STOCK|INSUFFICIENT_STOCK"},
              ...
          ]}
        """
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        results: List[Dict[str, Any]] = []

        # 事务自适应（避免 A transaction is already begun...）
        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            for idx, line in enumerate(lines, start=1):
                item_id = int(line["item_id"])
                loc_id = int(line["location_id"])
                need = int(line["qty"])

                # 1) 业务幂等登记（仅当解析到 store_id）
                idem_inserted = True
                if store_id is not None:
                    res = await session.execute(
                        text("""
                            INSERT INTO outbound_ship_ops (store_id, ref, item_id, location_id, qty)
                            VALUES (:sid, :ref, :iid, :loc, :qty)
                            ON CONFLICT ON CONSTRAINT uq_ship_idem_key DO NOTHING
                            RETURNING id
                        """),
                        {"sid": store_id, "ref": ref, "iid": item_id, "loc": loc_id, "qty": need},
                    )
                    idem_id = res.scalar_one_or_none()
                    idem_inserted = idem_id is not None

                # 无 store_id → 退化为台账幂等保护
                if store_id is None and await _ledger_exists(session, ref, item_id, loc_id, idx):
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "IDEMPOTENT"})
                    continue

                if not idem_inserted:
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "IDEMPOTENT"})
                    continue

                # 2) 真实出库：锁库存行、扣减、记账
                row = (
                    await session.execute(
                        select(Stock.id, Stock.qty)
                        .where(Stock.item_id == item_id, Stock.location_id == loc_id)
                        .with_for_update()
                    )
                ).first()

                if not row:
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "NO_STOCK"})
                    continue
                if int(row.qty) < need:
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "INSUFFICIENT_STOCK"})
                    continue

                # 兜底：台账重复检查
                if await _ledger_exists(session, ref, item_id, loc_id, idx):
                    results.append({"item_id": item_id, "location_id": loc_id, "qty": 0, "status": "IDEMPOTENT"})
                    continue

                after = int(row.qty) - need
                await session.execute(
                    text("UPDATE stocks SET qty=:after WHERE id=:sid"),
                    {"after": after, "sid": row.id},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO stock_ledger
                          (stock_id, item_id, delta, after_qty, occurred_at, reason, ref, ref_line)
                        VALUES
                          (:sid,:iid,:delta,:after,:ts,'OUTBOUND',:ref,:line)
                        """
                    ),
                    {
                        "sid": row.id,
                        "iid": item_id,
                        "delta": -need,
                        "after": after,
                        "ts": datetime.now(timezone.utc),
                        "ref": ref,
                        "line": idx,
                    },
                )

                if store_id is not None:
                    await ChannelInventoryService.adjust_reserved(
                        session, store_id=store_id, item_id=item_id, delta=-need
                    )

                results.append({"item_id": item_id, "location_id": loc_id, "qty": need, "status": "OK"})

        if store_id is not None and refresh_visible:
            ok_items = [r["item_id"] for r in results if r["status"] == "OK"]
            if ok_items:
                await StoreService.refresh_channel_inventory_for_store(
                    session, store_id=store_id, item_ids=ok_items, dry_run=False
                )

        return {"store_id": store_id, "ref": ref, "results": results}


# ---------------------------- helpers -------------------------------------

async def _resolve_store_id(
    session: AsyncSession, *, platform: str, shop_id: str
) -> Optional[int]:
    if not shop_id:
        return None
    row = (
        await session.execute(
            select(Store.id)
            .where(Store.platform == platform, Store.name == shop_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def _ledger_exists(
    session: AsyncSession, ref: str, item_id: int, location_id: int, ref_line: int
) -> bool:
    row = await session.execute(
        text("""
            SELECT 1
            FROM stock_ledger sl
            JOIN stocks s ON s.id = sl.stock_id
            WHERE sl.reason='OUTBOUND'
              AND sl.ref=:ref
              AND sl.ref_line=:line
              AND sl.item_id=:iid
              AND s.location_id=:loc
            LIMIT 1
        """),
        {"ref": ref, "line": ref_line, "iid": item_id, "loc": location_id},
    )
    return row.first() is not None


__all__ = ["OutboundService"]
