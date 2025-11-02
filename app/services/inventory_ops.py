# -*- coding: utf-8 -*-
"""
InventoryOpsService — 同仓搬运（src → dst）

统一签名（不做“自适应”）：
transfer(session, *, item_id, src_location_id, dst_location_id, qty, reason='PUTAWAY', ref=None, allow_expired=False)

要点：
- 严格同仓校验（locations.warehouse_id）
- FEFO 逐段搬运：源位“显式定批次出库” → 目标位“同批入库”
- 幂等闩：同一 (reason, ref) 已完成则直接返回 idempotent=True
- ★ 关键修复：出库前把源批次 batches.qty 同步为 stocks 汇总，避免“仅造 stocks 时判定库存不足”
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.stock_helpers import ensure_stock_slot
from app.services.stock_service import StockService


class InventoryOpsService:
    """库内搬运服务（同仓 src→dst），按 FEFO 分段执行。"""

    async def _warehouse_id(self, session: AsyncSession, loc_id: int) -> int:
        wid = (
            await session.execute(text("SELECT warehouse_id FROM locations WHERE id=:id"), {"id": loc_id})
        ).scalar_one_or_none()
        if wid is None:
            raise ValueError(f"location {loc_id} missing")
        return int(wid)

    async def _next_fefo(
        self,
        session: AsyncSession,
        item_id: int,
        src_location_id: int,
        allow_expired: bool,
    ) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT s.batch_code,
                   b.expiry_date,
                   s.qty
              FROM stocks s
         LEFT JOIN batches b
                ON b.item_id=s.item_id
               AND b.warehouse_id=s.warehouse_id
               AND b.location_id=s.location_id
               AND b.batch_code=s.batch_code
             WHERE s.item_id=:i
               AND s.location_id=:loc
               AND COALESCE(s.qty,0) > 0
        """
        if not allow_expired:
            sql += " AND (b.expiry_date IS NULL OR b.expiry_date >= CURRENT_DATE)\n"
        sql += " ORDER BY b.expiry_date NULLS LAST, s.batch_code LIMIT 1"

        m = (await session.execute(text(sql), {"i": item_id, "loc": src_location_id})).mappings().first()
        if not m:
            return None
        return {
            "batch_code": m["batch_code"],
            "expiry_date": m["expiry_date"],  # date | None
            "qty": int(m["qty"] or 0),
        }

    async def _dst_batch_id(self, session: AsyncSession, item_id: int, dst_location_id: int, batch_code: str) -> Optional[int]:
        v = (
            await session.execute(
                text("SELECT id FROM batches WHERE item_id=:i AND location_id=:l AND batch_code=:b"),
                {"i": item_id, "l": dst_location_id, "b": batch_code},
            )
        ).scalar_one_or_none()
        return int(v) if v is not None else None

    async def _sync_batch_qty(self, session: AsyncSession, item_id: int, location_id: int, batch_code: str) -> None:
        """
        将 batches.qty 同步为 stocks 同批汇总值（仅此处使用；不改变系统全局口径）。
        适用于测试/极简夹具只造 stocks 未造/未更新 batches 的情况。
        """
        await session.execute(
            text(
                """
                INSERT INTO batches(item_id, location_id, batch_code, qty)
                VALUES (:i, :l, :b, 0)
                ON CONFLICT (item_id, location_id, batch_code) DO NOTHING
                """
            ),
            {"i": item_id, "l": location_id, "b": batch_code},
        )
        await session.execute(
            text(
                """
                UPDATE batches tb
                   SET qty = sub.sum_qty
                  FROM (
                        SELECT COALESCE(SUM(qty),0)::bigint AS sum_qty
                          FROM stocks
                         WHERE item_id=:i AND location_id=:l AND batch_code=:b
                       ) sub
                 WHERE tb.item_id=:i AND tb.location_id=:l AND tb.batch_code=:b
                """
            ),
            {"i": item_id, "l": location_id, "b": batch_code},
        )

    async def transfer(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        src_location_id: int,
        dst_location_id: int,
        qty: int,
        reason: str = "PUTAWAY",
        ref: Optional[str] = None,
        allow_expired: bool = False,
    ) -> dict:
        if qty <= 0:
            raise AssertionError("qty must be positive")
        reason = (reason or "PUTAWAY").upper()

        # 幂等闩：同一 (reason, ref) 已完成两腿则直接返回
        if ref:
            cnt = (
                await session.execute(
                    text("SELECT COUNT(*) FROM stock_ledger WHERE reason=:r AND ref=:ref"),
                    {"r": reason, "ref": ref},
                )
            ).scalar()
            if int(cnt or 0) >= 2:
                return {"ok": True, "idempotent": True, "moved": 0, "moves": []}

        # 同仓校验
        src_w = await self._warehouse_id(session, src_location_id)
        dst_w = await self._warehouse_id(session, dst_location_id)
        if src_w != dst_w:
            raise ValueError(f"cross-warehouse transfer not allowed: {src_w} -> {dst_w}")

        remaining = int(qty)
        moved = 0
        moves: List[Dict[str, Any]] = []

        while remaining > 0:
            cand = await self._next_fefo(session, item_id, src_location_id, allow_expired=allow_expired)
            if not cand:
                break

            take = min(remaining, cand["qty"])
            batch_code: str = cand["batch_code"]
            expiry: Optional[date] = cand["expiry_date"] or (date.today() + timedelta(days=30))

            # 1) 源/目标批次槽位保证存在
            await ensure_stock_slot(session, item_id=item_id, warehouse_id=src_w, location_id=src_location_id, batch_code=batch_code)
            await ensure_stock_slot(session, item_id=item_id, warehouse_id=dst_w, location_id=dst_location_id, batch_code=batch_code)

            # 2) ★ 同步源批次 batches.qty = 同批 stocks 汇总，解除 FEFO 出库“库存不足”误判
            await self._sync_batch_qty(session, item_id=item_id, location_id=src_location_id, batch_code=batch_code)

            # 3) 源位“显式定批次”出库（绕过 FEFO 内部候选误差）
            await StockService().outbound_fefo(
                session=session,
                item_id=item_id,
                location_id=src_location_id,
                qty=int(take),
                reason=reason,
                ref=ref,
                allow_expired=allow_expired,
                batch_code=batch_code,
                allow_explicit_batch=True,
            )

            # 4) 目标位入库（同批）
            await InventoryAdjust.inbound(
                session=session,
                item_id=item_id,
                location_id=dst_location_id,
                delta=float(take),
                reason=reason,
                ref=ref,
                batch_code=batch_code,
                production_date=None,
                expiry_date=expiry,
            )

            dst_bid = await self._dst_batch_id(session, item_id, dst_location_id, batch_code)
            moves.append({"dst_batch_id": dst_bid, "qty": int(take), "batch_code": batch_code})
            moved += int(take)
            remaining -= int(take)

        return {
            "ok": True,
            "idempotent": False,
            "moved": moved,
            "total_moved": moved,
            "requested": int(qty),
            "moves": moves,
        }
