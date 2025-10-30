# app/services/stock_service.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.reconcile_service import ReconcileService
from app.services.stock_helpers import ensure_item


class StockService:
    """
    v1.0 门面服务（兼容增强版）
    - 入库/出库统一入口 adjust()
    - FEFO 调拨 transfer()，支持 allow_expired
    - 返回值兜底补齐：stock_after / batch_after
    """

    # ---------- 内部小工具 ----------
    async def _get_batch_qty(
        self, *, session: AsyncSession, item_id: int, location_id: int, batch_code: str
    ) -> int:
        row = await session.execute(
            text(
                """
                SELECT qty
                FROM batches
                WHERE item_id = :i AND location_id = :l AND batch_code = :b
            """
            ),
            {"i": item_id, "l": location_id, "b": batch_code},
        )
        v = row.scalar_one_or_none()
        return int(v or 0)

    async def _get_batch_id(
        self, *, session: AsyncSession, item_id: int, location_id: int, batch_code: str
    ) -> Optional[int]:
        row = await session.execute(
            text(
                """
                SELECT id
                FROM batches
                WHERE item_id = :i AND location_id = :l AND batch_code = :b
            """
            ),
            {"i": item_id, "l": location_id, "b": batch_code},
        )
        v = row.scalar_one_or_none()
        return int(v) if v is not None else None

    async def _get_stocks_sum(
        self, *, session: AsyncSession, item_id: int, location_id: int
    ) -> int:
        row = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0)
                FROM stocks
                WHERE item_id = :i AND location_id = :l
            """
            ),
            {"i": item_id, "l": location_id},
        )
        return int(row.scalar_one() or 0)

    async def _get_location_wh(self, *, session: AsyncSession, location_id: int) -> int:
        row = await session.execute(
            text("SELECT warehouse_id FROM locations WHERE id=:id"), {"id": location_id}
        )
        wid = row.scalar_one_or_none()
        if wid is None:
            raise ValueError(f"location {location_id} missing")
        return int(wid)

    async def _next_fefo_candidate(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        src_location_id: int,
        allow_expired: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        取源库位下一支 FEFO 候选（qty>0）。
        - allow_expired=False 时跳过已过期批次
        - 返回: {batch_code, expiry_date, qty, warehouse_id}
        """
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

        row = await session.execute(text(sql), {"i": item_id, "loc": src_location_id})
        m = row.mappings().first()
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
            # 出库：默认 FEFO；仅当允许且传入 batch_code 时定向批次
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
                res["stock_after"] = await self._get_stocks_sum(
                    session=session, item_id=item_id, location_id=location_id
                )
            return res

        # 入库
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

        if res.get("batch_after") is None:
            res["batch_after"] = await self._get_batch_qty(
                session=session, item_id=item_id, location_id=location_id, batch_code=batch_code
            )

        return res

    # ---------- 便捷别名 ----------
    async def inbound(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        qty: int,
        reason: str = "INBOUND",
        ref: Optional[str] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        return await self.adjust(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=abs(qty),
            reason=reason,
            ref=ref,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

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
        src_location_id: int,
        dst_location_id: int,
        qty: int,
        allow_expired: bool = False,
        reason: str = "TRANSFER",
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从 src_location_id 调拨 qty 到 dst_location_id（同仓），按 FEFO 批次逐段搬运。
        - allow_expired=False: 跳过已过期批次
        - 每段：源定向出库指定批次 → 目标入库同批次（保留 expiry）
        返回：
          {
            "ok": True,
            "total_moved": X,         # 兼容测试断言
            "moved": X,               # 保留老字段
            "requested": qty,
            "moves": [                # 分段明细（用于断言 NEAR=7, FAR=3）
              {"dst_batch_id": <int>, "qty": <int>, "batch_code": "<code>"}
            ]
          }
        """
        if qty <= 0:
            raise AssertionError("qty must be positive")

        await ensure_item(session, item_id=item_id)
        reason = (reason or "TRANSFER").upper()

        # 同仓校验
        src_wid = await self._get_location_wh(session=session, location_id=src_location_id)
        dst_wid = await self._get_location_wh(session=session, location_id=dst_location_id)
        if src_wid != dst_wid:
            raise ValueError(f"cross-warehouse transfer not allowed: {src_wid} -> {dst_wid}")

        remaining = int(qty)
        moved = 0
        moves: List[Dict[str, Any]] = []

        while remaining > 0:
            cand = await self._next_fefo_candidate(
                session=session,
                item_id=item_id,
                src_location_id=src_location_id,
                allow_expired=allow_expired,
            )
            if not cand:
                break  # 源没有可用批次或只剩下不允许的过期批

            take = min(remaining, cand["qty"])
            batch_code = cand["batch_code"]
            expiry_date = cand["expiry_date"]

            # 源定向出库（指定批次，保证与入库对齐）
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

            # 目标入库同批次
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

            # 查询目标批次 id，记录分段明细
            dst_bid = await self._get_batch_id(
                session=session,
                item_id=item_id,
                location_id=dst_location_id,
                batch_code=batch_code,
            )
            moves.append({"dst_batch_id": dst_bid, "qty": int(take), "batch_code": batch_code})

            moved += take
            remaining -= take

        return {
            "ok": True,
            "total_moved": moved,
            "moved": moved,
            "requested": int(qty),
            "moves": moves,
        }

    # ---------- 可选提交 ----------
    async def adjust_and_commit(self, **kwargs) -> Dict[str, Any]:
        session: AsyncSession = kwargs["session"]
        res = await self.adjust(**kwargs)
        await session.flush()
        await session.commit()
        return res

    # ---------- 可用量查询 ----------
    async def available(
        self, *, session: AsyncSession, item_id: int, location_id: int
    ) -> Dict[str, int]:
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
            return {
                "item_id": item_id,
                "location_id": location_id,
                "on_hand": 0,
                "reserved": 0,
                "available": 0,
            }
        return {
            "item_id": item_id,
            "location_id": location_id,
            "on_hand": int(m["on_hand"] or 0),
            "reserved": int(m["reserved"] or 0),
            "available": int(m["available"] or 0),
        }

    # ---------- 盘点对账 ----------
    async def reconcile_inventory(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        counted_qty: float,
        apply: bool = True,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await ReconcileService.reconcile_inventory(
            session=session,
            item_id=item_id,
            location_id=location_id,
            counted_qty=counted_qty,
            apply=apply,
            ref=ref,
        )
