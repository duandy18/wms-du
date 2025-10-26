# app/services/outbound_service.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

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
        warehouse_id: int | None = None,  # Phase 4 以后启用；v1.0 单仓忽略
    ) -> Dict:
        """
        精简出库：
          - 扣减 stocks.qty（逐行 FOR UPDATE）
          - 写 stock_ledger（reason='OUTBOUND'）
          - -reserved（按本次发货量负向冲销渠道占用）
          - 可选：刷新 visible_qty（A 策略）

        参数：
          lines = [{"item_id": 1, "location_id": 10, "qty": 5}, ...]
        返回：
          {"store_id": <int|None>, "ref": <str>, "results": [{"item_id", "qty", "status"}]}
        """
        store_id = await _resolve_store_id(session, platform=platform, shop_id=shop_id)
        results: List[Dict] = []

        # 关键修复：根据 Session 状态选择 begin / begin_nested，避免 “A transaction is already begun…”
        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            for idx, line in enumerate(lines, start=1):
                item_id = int(line["item_id"])
                loc_id = int(line["location_id"])
                need = int(line["qty"])

                # 锁定库存行
                row = (
                    await session.execute(
                        select(Stock.id, Stock.qty)
                        .where(Stock.item_id == item_id, Stock.location_id == loc_id)
                        .with_for_update()
                    )
                ).first()

                if not row:
                    results.append({"item_id": item_id, "qty": 0, "status": "NO_STOCK"})
                    continue
                if int(row.qty) < need:
                    results.append({"item_id": item_id, "qty": 0, "status": "INSUFFICIENT"})
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
                        "ts": datetime.utcnow(),
                        "ref": ref,
                        "line": idx,
                    },
                )

                # 渠道侧：按发货量做负向冲销（若无匹配 store_id 则跳过，不阻断）
                if store_id is not None:
                    await ChannelInventoryService.adjust_reserved(
                        session, store_id=store_id, item_id=item_id, delta=-need
                    )

                results.append({"item_id": item_id, "qty": need, "status": "OK"})

        # 可选刷新可见量（A 策略，按本次发生的 OK 行）
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
    """
    最小解析策略：
      - stores 表按 (platform, name=shop_id) 匹配一条；
      - 找不到则返回 None（跳过渠道侧同步，不阻断）。
    """
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


__all__ = ["OutboundService"]
