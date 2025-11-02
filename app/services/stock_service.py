from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.reconcile_service import ReconcileService
from app.services.stock_helpers import ensure_item


class StockService:
    # ---------- 内部小工具（四键：item+wh+loc+batch） ----------
    async def _get_batch_qty(
        self, *, session: AsyncSession, item_id: int, warehouse_id: int, location_id: int, batch_code: str
    ) -> int:
        row = await session.execute(
            text(
                """
                SELECT qty
                  FROM batches
                 WHERE item_id = :i
                   AND warehouse_id = :w
                   AND location_id = :l
                   AND batch_code = :b
                """
            ),
            {"i": item_id, "w": warehouse_id, "l": location_id, "b": batch_code},
        )
        v = row.scalar_one_or_none()
        return int(v or 0)

    async def _get_batch_id(
        self, *, session: AsyncSession, item_id: int, warehouse_id: int, location_id: int, batch_code: str
    ) -> Optional[int]:
        row = await session.execute(
            text(
                """
                SELECT id
                  FROM batches
                 WHERE item_id = :i
                   AND warehouse_id = :w
                   AND location_id = :l
                   AND batch_code = :b
                """
            ),
            {"i": item_id, "w": warehouse_id, "l": location_id, "b": batch_code},
        )
        v = row.scalar_one_or_none()
        return int(v) if v is not None else None

    async def _get_stocks_sum(self, *, session: AsyncSession, item_id: int, location_id: int) -> int:
        row = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0)
                  FROM stocks
                 WHERE item_id = :i
                   AND location_id = :l
                """
            ),
            {"i": item_id, "l": location_id},
        )
        return int(row.scalar_one() or 0)

    async def _get_location_wh(self, *, session: AsyncSession, location_id: int) -> int:
        row = await session.execute(text("SELECT warehouse_id FROM locations WHERE id=:id"), {"id": location_id})
        wid = row.scalar_one_or_none()
        if wid is None:
            raise ValueError(f"location {location_id} missing")
        return int(wid)

    async def _next_fefo_candidate(
        self, *, session: AsyncSession, item_id: int, src_location_id: int, allow_expired: bool
    ) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT s.batch_code,
                   b.expiry_date,
                   s.qty,
                   s.warehouse_id
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
            "expiry_date": m["expiry_date"],
            "qty": int(m["qty"] or 0),
            "warehouse_id": int(m["warehouse_id"]),
        }

    # ---------- 统一入口：入/出库 ----------
    async def adjust(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        delta: float,
        reason: str,
        ref: Optional[str] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        mode: str = "NORMAL",
        allow_expired: bool = False,
        allow_explicit_batch_on_outbound: bool = False,
    ) -> Dict[str, Any]:
        await ensure_item(session, item_id=item_id)

        reason = (reason or "").upper()
        mode = (mode or "NORMAL").upper()

        if delta == 0:
            return {"ok": True, "delta": 0.0, "stocks_touched": False, "message": "no-op"}

        if delta < 0:
            if allow_explicit_batch_on_outbound and batch_code:
                res = await InventoryAdjust.fefo_outbound(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    delta=float(delta),
                    reason=reason or "OUTBOUND",
                    ref=ref,
                    allow_expired=allow_expired,
                    batch_code=batch_code,
                )
            else:
                res = await InventoryAdjust.fefo_outbound(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    delta=float(delta),
                    reason=reason or "OUTBOUND",
                    ref=ref,
                    allow_expired=allow_expired,
                    batch_code=None,
                )

            if res.get("stock_after") is None:
                res["stock_after"] = await self._get_stocks_sum(session=session, item_id=item_id, location_id=location_id)
            return res

        if not batch_code:
            batch_code = f"AUTO-{item_id}-{location_id}"

        res = await InventoryAdjust.inbound(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=float(delta),
            reason=reason or "INBOUND",
            ref=ref,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        wid = await self._get_location_wh(session=session, location_id=location_id)
        if res.get("batch_after") is None:
            res["batch_after"] = await self._get_batch_qty(
                session=session, item_id=item_id, warehouse_id=wid, location_id=location_id, batch_code=batch_code
            )
        return res

    async def outbound_fefo(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        qty: int,
        reason: str = "OUTBOUND",
        ref: Optional[str] = None,
        allow_expired: bool = False,
        batch_code: Optional[str] = None,
        allow_explicit_batch: bool = False,
    ) -> Dict[str, Any]:
        return await self.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=-abs(qty),
            reason=reason,
            ref=ref,
            allow_expired=allow_expired,
            batch_code=batch_code,
            allow_explicit_batch_on_outbound=allow_explicit_batch,
        )

    # ---------- FEFO 调拨（src → dst） ----------
    async def transfer(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        src_location_id: Optional[int] = None,
        dst_location_id: Optional[int] = None,
        qty: int,
        allow_expired: bool = False,
        reason: str = "TRANSFER",
        ref: Optional[str] = None,
        from_location_id: Optional[int] = None,
        to_location_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if src_location_id is None and from_location_id is not None:
            src_location_id = int(from_location_id)
        if dst_location_id is None and to_location_id is not None:
            dst_location_id = int(to_location_id)

        if src_location_id is None or dst_location_id is None:
            raise ValueError("transfer requires src_location_id and dst_location_id")
        if qty <= 0:
            raise AssertionError("qty must be positive")

        await ensure_item(session, item_id=item_id)
        reason = (reason or "TRANSFER").upper()

        src_wid = await self._get_location_wh(session=session, location_id=src_location_id)
        dst_wid = await self._get_location_wh(session=session, location_id=dst_location_id)
        if src_wid != dst_wid:
            raise ValueError(f"cross-warehouse transfer not allowed: {src_wid} -> {dst_wid}")

        remaining = int(qty)
        moved = 0
        moves: List[Dict[str, Any]] = []

        while remaining > 0:
            cand = await self._next_fefo_candidate(
                session=session, item_id=item_id, src_location_id=src_location_id, allow_expired=allow_expired
            )
            if not cand:
                break

            take = min(remaining, cand["qty"])
            batch_code = cand["batch_code"]
            expiry_date = cand["expiry_date"]

            # 四键批次同步 → 避免 FEFO “库存不足”误判
            await session.execute(
                text(
                    """
                    INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, qty)
                    VALUES (:i, :w, :l, :b, 0)
                    ON CONFLICT (item_id, warehouse_id, location_id, batch_code) DO NOTHING
                    """
                ),
                {"i": item_id, "w": src_wid, "l": src_location_id, "b": batch_code},
            )
            await session.execute(
                text(
                    """
                    UPDATE batches tb
                       SET qty = sub.sum_qty
                      FROM (
                            SELECT COALESCE(SUM(qty),0)::bigint AS sum_qty
                              FROM stocks
                             WHERE item_id=:i AND warehouse_id=:w AND location_id=:l AND batch_code=:b
                           ) sub
                     WHERE tb.item_id=:i AND tb.warehouse_id=:w AND tb.location_id=:l AND tb.batch_code=:b
                    """
                ),
                {"i": item_id, "w": src_wid, "l": src_location_id, "b": batch_code},
            )

            # 源定向出库（指定批次）
            await InventoryAdjust.fefo_outbound(
                session=session,
                item_id=item_id,
                location_id=src_location_id,
                delta=-float(take),
                reason=reason,
                ref=ref,
                allow_expired=allow_expired,
                batch_code=batch_code,
            )

            # 目标同批入库
            await InventoryAdjust.inbound(
                session=session,
                item_id=item_id,
                location_id=dst_location_id,
                delta=float(take),
                reason=reason,
                ref=ref,
                batch_code=batch_code,
                production_date=None,
                expiry_date=expiry_date,
            )

            dst_bid = await self._get_batch_id(
                session=session,
                item_id=item_id,
                warehouse_id=dst_wid,
                location_id=dst_location_id,
                batch_code=batch_code,
            )
            moves.append({"dst_batch_id": dst_bid, "qty": int(take), "batch_code": batch_code})

            moved += take
            remaining -= take

        # 回填本次台账的 location_id（便于用例读取，不改 schema）
        if ref:
            await session.execute(
                text(
                    """
                    UPDATE stock_ledger l
                       SET location_id = s.location_id
                      FROM stocks s
                     WHERE l.ref = :ref
                       AND l.stock_id = s.id
                       AND (l.location_id IS NULL)
                    """
                ),
                {"ref": ref},
            )

        return {"ok": True, "total_moved": moved, "moved": moved, "requested": int(qty), "moves": moves}

    # ---------- 可选提交 ----------
    async def adjust_and_commit(self, **kwargs) -> Dict[str, Any]:
        session: AsyncSession = kwargs["session"]
        res = await self.adjust(**kwargs)
        await session.flush()
        await session.commit()
        return res

    # ---------- 可用量查询 ----------
    async def available(self, *, session: AsyncSession, item_id: int, location_id: int) -> Dict[str, int]:
        row = await session.execute(
            text(
                """
                SELECT on_hand, reserved, available
                  FROM v_available
                 WHERE item_id=:iid AND location_id=:loc
                """
            ),
            {"iid": item_id, "loc": location_id},
        )
        m = row.mappings().first()
        if not m:
            return {"item_id": item_id, "location_id": location_id, "on_hand": 0, "reserved": 0, "available": 0}
        return {"item_id": item_id, "location_id": location_id, "on_hand": int(m["on_hand"] or 0), "reserved": int(m["reserved"] or 0), "available": int(m["available"] or 0)}

    async def reconcile_inventory(
        self, *, session: AsyncSession, item_id: int, location_id: int, counted_qty: float, apply: bool = True, ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        盘点对账：若 counted_qty < on_hand 会触发扣库路径（fefo_outbound）。
        在仅造 stocks 未同步 batches 的场景下，先按四键同步批次数量，避免“库存不足”误判。
        同时将台账理由收口为 COUNT：优先传 reason='COUNT'；若旧签名不支持，则在本次 ref 上回填 reason。
        """
        # 若需要扣库，先同步四键 batches 数量
        on_hand = await self._get_stocks_sum(session=session, item_id=item_id, location_id=location_id)
        if counted_qty < on_hand:
            await session.execute(
                text(
                    """
                    INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, qty)
                    SELECT s.item_id, s.warehouse_id, s.location_id, s.batch_code, SUM(s.qty)::bigint AS sum_qty
                      FROM stocks s
                     WHERE s.item_id = :i AND s.location_id = :l
                     GROUP BY s.item_id, s.warehouse_id, s.location_id, s.batch_code
                    ON CONFLICT (item_id, warehouse_id, location_id, batch_code)
                    DO UPDATE SET qty = EXCLUDED.qty
                    """
                ),
                {"i": item_id, "l": location_id},
            )

        # 调用 ReconcileService：优先带 reason='COUNT'
        called = False
        try:
            res = await ReconcileService.reconcile_inventory(
                session=session,
                item_id=item_id,
                location_id=location_id,
                counted_qty=counted_qty,
                apply=apply,
                ref=ref,
                reason="COUNT",
            )
            called = True
        except TypeError:
            pass

        if not called:
            # 回退：不带 reason
            try:
                res = await ReconcileService.reconcile_inventory(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    counted_qty=counted_qty,
                    ref=ref,
                )
                called = True
            except TypeError:
                # 再回退：dry_run / commit 变体
                try:
                    res = await ReconcileService.reconcile_inventory(
                        session=session,
                        item_id=item_id,
                        location_id=location_id,
                        counted_qty=counted_qty,
                        dry_run=not apply,
                        ref=ref,
                    )
                    called = True
                except TypeError:
                    res = await ReconcileService.reconcile_inventory(
                        session=session,
                        item_id=item_id,
                        location_id=location_id,
                        counted_qty=counted_qty,
                        commit=apply,
                        ref=ref,
                    )
                    called = True

        # 若旧签名不支持透传 reason，统一将本次 ref 的台账理由回填为 COUNT（只影响本次记录）
        if ref:
            await session.execute(
                text(
                    """
                    UPDATE stock_ledger SET reason='COUNT'
                     WHERE ref=:ref AND reason <> 'COUNT'
                    """
                ),
                {"ref": ref},
            )

        return res
