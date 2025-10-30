# app/services/inventory_ops.py
# -*- coding: utf-8 -*-
"""
InventoryOpsService — 同仓搬运（A库位 → B库位）

修正版：
- 不再显式使用 session.begin()（pytest fixture 已开启事务）
- 整个搬运过程按顺序执行一次 出 / 入
- Ledger、stocks 均守恒
- 新增：同一 (reason, ref) 的幂等闩（已完成一次 MOVE 的第二次调用将被跳过）
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.stock_helpers import ensure_stock_slot


class InventoryOpsService:
    """库内搬运服务（同仓 from→to）。"""

    async def transfer(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        reason: str = "MOVE",
        ref: Optional[str] = None,
    ) -> dict:
        if qty <= 0:
            raise AssertionError("qty must be positive")

        # 0) 规范化
        reason = (reason or "MOVE").upper()

        # 0.5) 幂等闩：若该 ref 的 MOVE 已完成一次（应有两条台账：源-负/目的-正），则直接返回
        if ref:
            existing = await session.execute(
                text("SELECT COUNT(*) FROM stock_ledger WHERE reason = :reason AND ref = :ref"),
                {"reason": reason, "ref": ref},
            )
            if int(existing.scalar() or 0) >= 2:
                return {"ok": True, "idempotent": True, "moved": 0}

        # 1. 获取仓号，确保目标库位存在
        wid_from = (
            await session.execute(
                text("SELECT warehouse_id FROM locations WHERE id=:id"), {"id": from_location_id}
            )
        ).scalar()
        if wid_from is None:
            raise ValueError(f"location {from_location_id} missing")

        wid_to = (
            await session.execute(
                text("SELECT warehouse_id FROM locations WHERE id=:id"), {"id": to_location_id}
            )
        ).scalar()
        if wid_to is None:
            wid_to = wid_from
            await session.execute(
                text(
                    "INSERT INTO locations(id, name, warehouse_id) VALUES(:id, :n, :w) ON CONFLICT(id) DO NOTHING"
                ),
                {"id": to_location_id, "n": f"LOC-{to_location_id}", "w": wid_to},
            )

        if wid_from != wid_to:
            raise ValueError(f"cross-warehouse transfer not allowed: {wid_from} -> {wid_to}")

        # 2. 获取源批次（FEFO）
        row = await session.execute(
            text(
                """
                SELECT s.batch_code, b.expiry_date
                  FROM stocks s
             LEFT JOIN batches b
                    ON b.item_id=s.item_id
                   AND b.warehouse_id=s.warehouse_id
                   AND b.location_id=s.location_id
                   AND b.batch_code=s.batch_code
                 WHERE s.item_id=:i AND s.warehouse_id=:w AND s.location_id=:l
                   AND COALESCE(s.qty,0) > 0
              ORDER BY b.expiry_date NULLS LAST, s.batch_code
                 LIMIT 1
            """
            ),
            {"i": item_id, "w": wid_from, "l": from_location_id},
        )
        first = row.mappings().first()
        if not first:
            raise ValueError(f"no available stock to move for item {item_id}")
        batch_code = first["batch_code"]
        expiry = first["expiry_date"] or (date.today() + timedelta(days=30))

        # 3. 预建目标槽位
        await ensure_stock_slot(
            session,
            item_id=item_id,
            warehouse_id=wid_to,
            location_id=to_location_id,
            batch_code=batch_code,
        )

        # 4. 顺序执行：出 + 入（不嵌套事务）
        await InventoryAdjust.fefo_outbound(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-float(qty),
            reason=reason,
            ref=ref,
            allow_expired=False,
            batch_code=batch_code,
        )

        await InventoryAdjust.inbound(
            session=session,
            item_id=item_id,
            location_id=to_location_id,
            delta=float(qty),
            reason=reason,
            ref=ref,
            batch_code=batch_code,
            production_date=None,
            expiry_date=expiry,
        )

        return {"ok": True, "idempotent": False, "moved": int(qty)}
