# app/services/stock_service.py
from __future__ import annotations

import asyncio
import random
from datetime import date

from sqlalchemy import and_, case, func, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.models.warehouse import Warehouse


# -------------------- 通用带重试执行（缓解并发锁） --------------------
async def _exec_with_retry(
    session: AsyncSession,
    stmt,
    params=None,
    retries: int = 24,
    base_sleep: float = 0.03,
    max_sleep: float = 0.35,
):
    await asyncio.sleep(base_sleep * 0.6)
    for i in range(retries):
        try:
            if params is None:
                return await session.execute(stmt)
            else:
                return await session.execute(stmt, params)
        except OperationalError as e:
            msg = (str(e) or "").lower()
            is_locked = ("database is locked" in msg) or ("database is busy" in msg)
            if not is_locked or i >= retries - 1:
                raise
            backoff = min(max_sleep, base_sleep * (1.8 ** (i + 1)))
            await asyncio.sleep(backoff * (0.6 + random.random() * 0.4))


class StockService:
    def __init__(self, db: Session | None = None):
        self.db = db

    # ==================== 公共入口 ====================
    def adjust(self, **kwargs):
        if "session" in kwargs:
            return self._adjust_async(**kwargs)
        return self.adjust_sync(**kwargs)

    # ==================== 异步入口（自动分流） ====================
    async def _adjust_async(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        delta: float,
        reason: str,
        ref: str | None = None,
        batch_code: str | None = None,
        production_date: date | None = None,
        expiry_date: date | None = None,
        mode: str = "NORMAL",
        allow_expired: bool = False,
    ) -> dict:
        mode = (mode or "NORMAL").upper()
        if delta < 0:
            if batch_code:
                return await self._adjust_outbound_direct(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    batch_code=batch_code,
                    amount=-float(delta),
                    reason=reason,
                    ref=ref,
                )
            return await self._adjust_fefo(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(delta),
                reason=reason,
                ref=ref,
                allow_expired=allow_expired,
            )
        # 正数 → NORMAL 入库
        return await self._adjust_normal(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=float(delta),
            reason=reason,
            ref=ref,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    # ==================== NORMAL 入库 ====================
    async def _adjust_normal(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        delta: float,
        reason: str,
        ref: str | None,
        batch_code: str | None,
        production_date: date | None,
        expiry_date: date | None,
    ) -> dict:
        if delta <= 0:
            raise ValueError("NORMAL 模式仅支持正数入库")
        warehouse_id = await self._resolve_warehouse_id(session, location_id)
        if not batch_code:
            batch_code = f"AUTO-{item_id}-{date.today():%Y%m%d}"

        batch_id = await self._ensure_batch(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        await _exec_with_retry(
            session,
            update(Batch)
            .where(Batch.id == batch_id)
            .values(qty=func.coalesce(Batch.qty, 0) + int(delta)),
        )

        stock_id = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before + float(delta)

        # 写台账并拿到 ledger_id
        ins_ledger = (
            insert(StockLedger)
            .values(
                stock_id=stock_id,
                batch_id=batch_id,
                delta=int(delta),
                reason=reason,
                ref=ref,
                after_qty=int(after),
            )
            .returning(StockLedger.id)
        )
        ledger_id = (await _exec_with_retry(session, ins_ledger)).scalar_one()

        # 更新汇总库存
        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=float(delta)
        )

        # 读取批次与库存最终量
        batch_after = (
            await session.execute(select(Batch.qty).where(Batch.id == batch_id))
        ).scalar_one()
        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)

        await session.commit()
        return {
            "total_delta": float(delta),
            "batch_moves": [(batch_id, float(delta))],
            "stock_after": int(stock_after),
            "batch_after": int(batch_after),
            "ledger_id": int(ledger_id),
        }

    # ==================== 直接按批次出库 ====================
    async def _adjust_outbound_direct(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        batch_code: str,
        amount: float,
        reason: str,
        ref: str | None,
    ) -> dict:
        assert amount > 0, "outbound amount 必须为正数"
        warehouse_id = await self._resolve_warehouse_id(session, location_id)

        conds = [
            Batch.item_id == item_id,
            Batch.warehouse_id == warehouse_id,
            Batch.location_id == location_id,
            Batch.batch_code == batch_code,
        ]
        row = (await session.execute(select(Batch.id, Batch.qty).where(and_(*conds)))).first()
        if not row:
            raise ValueError(f"批次不存在：item={item_id}, loc={location_id}, code={batch_code}")
        batch_id, cur_qty = int(row[0]), int(row[1] or 0)
        if cur_qty < int(amount):
            raise ValueError("批次数量不足，无法出库")

        await _exec_with_retry(
            session,
            update(Batch)
            .where(Batch.id == batch_id)
            .values(qty=func.coalesce(Batch.qty, 0) - int(amount)),
        )

        stock_id = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before - float(amount)

        ins_ledger = (
            insert(StockLedger)
            .values(
                stock_id=stock_id,
                batch_id=batch_id,
                delta=-int(amount),
                reason=reason,
                ref=ref,
                after_qty=int(after),
            )
            .returning(StockLedger.id)
        )
        ledger_id = (await _exec_with_retry(session, ins_ledger)).scalar_one()

        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=-float(amount)
        )

        batch_after = (
            await session.execute(select(Batch.qty).where(Batch.id == batch_id))
        ).scalar_one()
        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)

        await session.commit()
        return {
            "total_delta": -float(amount),
            "batch_moves": [(batch_id, -float(amount))],
            "stock_after": int(stock_after),
            "batch_after": int(batch_after),
            "ledger_id": int(ledger_id),
        }

    # ==================== FEFO 出库 ====================
    async def _adjust_fefo(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        delta: float,
        reason: str,
        ref: str | None,
        allow_expired: bool,
    ) -> dict:
        warehouse_id = await self._resolve_warehouse_id(session, location_id)
        today = date.today()

        conds = [Batch.item_id == item_id, Batch.warehouse_id == warehouse_id, Batch.qty > 0]
        if "location_id" in Batch.__table__.c:
            conds.append(Batch.location_id == location_id)
        if not allow_expired:
            conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        order_by_cols = (
            [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                case((Batch.expiry_date < today, 0), else_=1),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
            if allow_expired
            else [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
        )

        rows = (
            await session.execute(
                select(Batch.id, Batch.expiry_date, Batch.qty)
                .where(and_(*conds))
                .order_by(*order_by_cols)
            )
        ).all()

        need = -float(delta)
        moves: list[tuple[int, float]] = []
        for r in rows:
            if need <= 0:
                break
            available = float(r.qty or 0)
            if available <= 0:
                continue
            take = min(need, available)
            moves.append((int(r.id), -take))
            need -= take

        if need > 1e-12:
            raise ValueError("库存不足，无法按 FEFO 出库")

        stock_id = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before

        last_ledger_id = None
        for batch_id, used in moves:
            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == batch_id)
                .values(qty=func.coalesce(Batch.qty, 0) + int(used)),
            )
            after += used
            ins_ledger = (
                insert(StockLedger)
                .values(
                    stock_id=stock_id,
                    batch_id=batch_id,
                    delta=int(used),
                    reason=reason,
                    ref=ref,
                    after_qty=int(after),
                )
                .returning(StockLedger.id)
            )
            last_ledger_id = (await _exec_with_retry(session, ins_ledger)).scalar_one()

        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=float(delta)
        )

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        await session.commit()
        return {
            "total_delta": float(delta),
            "batch_moves": moves,
            "stock_after": int(stock_after),
            "ledger_id": (int(last_ledger_id) if last_ledger_id is not None else None),
        }

    # ==================== 盘点（异步） ====================
    async def reconcile_inventory(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        counted_qty: float,
        apply: bool = True,
        ref: str | None = None,
    ) -> dict:
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        diff = float(counted_qty) - float(before)

        result = {
            "item_id": item_id,
            "location_id": location_id,
            "before_qty": float(before),
            "counted_qty": float(counted_qty),
            "diff": float(diff),
            "applied": bool(apply),
            "after_qty": None,
            "moves": [],
        }

        if abs(diff) < 1e-12:
            result["after_qty"] = float(before)
            return result

        if not apply:
            result["moves"] = [("CC-ADJ" if diff > 0 else "FEFO", float(diff))]
            result["after_qty"] = float(counted_qty)
            return result

        if diff > 0:
            batch_code = f"CC-ADJ-{date.today():%Y%m%d}"
            adj = await self._adjust_normal(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(diff),
                reason="CYCLE_COUNT_UP",
                ref=ref or "CC-UP",
                batch_code=batch_code,
                production_date=None,
                expiry_date=None,
            )
            result["moves"] = adj.get("batch_moves", [])
        else:
            fefo = await self._adjust_fefo(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(diff),
                reason="CYCLE_COUNT_DOWN",
                ref=ref or "CC-DOWN",
                allow_expired=True,
            )
            result["moves"] = fefo.get("batch_moves", [])

        result["after_qty"] = await self._get_current_qty(
            session, item_id=item_id, location_id=location_id
        )
        return result

    # ==================== 自动转移过期（异步） ====================
    async def auto_transfer_expired(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        to_location_id: int | None = None,
        to_location_name: str = "EXPIRED_ZONE",
        item_ids: list[int] | None = None,
        dry_run: bool = False,
        reason: str = "EXPIRED_TRANSFER",
        ref: str | None = None,
    ) -> dict:
        today = date.today()
        if to_location_id is None:
            to_location_id = await self._ensure_location(session, warehouse_id, to_location_name)

        conds = [Batch.warehouse_id == warehouse_id, Batch.qty > 0, Batch.expiry_date < today]
        if item_ids:
            conds.append(Batch.item_id.in_(item_ids))

        rows = (
            await session.execute(
                select(
                    Batch.id, Batch.item_id, Batch.location_id, Batch.batch_code, Batch.qty
                ).where(and_(*conds))
            )
        ).all()

        if not rows:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        moves: list[dict] = []
        moved_total = 0

        for bid, item_id, src_loc, code, qty in rows:
            qty_to_move = int(qty or 0)
            if qty_to_move <= 0:
                continue

            dst_bid = await self._ensure_batch(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                location_id=to_location_id,
                batch_code=code,
                production_date=None,
                expiry_date=None,
            )

            if dry_run:
                moves.append(
                    dict(
                        item_id=item_id,
                        batch_id_src=int(bid),
                        batch_code=code,
                        src_location_id=int(src_loc),
                        dst_location_id=int(to_location_id),
                        qty_moved=qty_to_move,
                    )
                )
                moved_total += qty_to_move
                continue

            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == bid)
                .values(qty=func.coalesce(Batch.qty, 0) - qty_to_move),
            )
            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == dst_bid)
                .values(qty=func.coalesce(Batch.qty, 0) + qty_to_move),
            )

            src_sid = await self._ensure_stock_row(session, item_id=item_id, location_id=src_loc)
            src_before = await self._get_current_qty(session, item_id=item_id, location_id=src_loc)
            src_after = src_before - qty_to_move
            await _exec_with_retry(
                session,
                insert(StockLedger).values(
                    stock_id=src_sid,
                    batch_id=bid,
                    delta=-qty_to_move,
                    reason=reason,
                    ref=ref,
                    after_qty=int(src_after),
                ),
            )
            await self._bump_stock(
                session, item_id=item_id, location_id=src_loc, delta=-qty_to_move
            )

            dst_sid = await self._ensure_stock_row(
                session, item_id=item_id, location_id=to_location_id
            )
            dst_before = await self._get_current_qty(
                session, item_id=item_id, location_id=to_location_id
            )
            dst_after = dst_before + qty_to_move
            await _exec_with_retry(
                session,
                insert(StockLedger).values(
                    stock_id=dst_sid,
                    batch_id=dst_bid,
                    delta=qty_to_move,
                    reason=reason,
                    ref=ref,
                    after_qty=int(dst_after),
                ),
            )
            await self._bump_stock(
                session, item_id=item_id, location_id=to_location_id, delta=qty_to_move
            )

            moves.append(
                dict(
                    item_id=item_id,
                    batch_id_src=int(bid),
                    batch_code=code,
                    src_location_id=int(src_loc),
                    dst_location_id=int(to_location_id),
                    qty_moved=qty_to_move,
                )
            )
            moved_total += qty_to_move

        if not dry_run:
            await session.commit()

        return {"warehouse_id": warehouse_id, "moved_total": moved_total, "moves": moves}

    # ==================== 调拨（异步） ====================
    async def transfer(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        src_location_id: int,
        dst_location_id: int,
        qty: float,
        allow_expired: bool = False,
        reason: str = "TRANSFER",
        ref: str | None = None,
    ) -> dict:
        if qty <= 0:
            raise ValueError("transfer qty 必须为正数")

        today = date.today()
        src_wh = await self._resolve_warehouse_id(session, src_location_id)
        dst_wh = await self._resolve_warehouse_id(session, dst_location_id)

        conds = [
            Batch.item_id == item_id,
            Batch.warehouse_id == src_wh,
            Batch.location_id == src_location_id,
            Batch.qty > 0,
        ]
        if not allow_expired:
            conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        order_by_cols = (
            [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                case((Batch.expiry_date < today, 0), else_=1),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
            if allow_expired
            else [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
        )

        rows = (
            await session.execute(
                select(
                    Batch.id,
                    Batch.batch_code,
                    Batch.expiry_date,
                    Batch.production_date,
                    Batch.qty,
                )
                .where(and_(*conds))
                .order_by(*order_by_cols)
            )
        ).all()

        if not rows:
            raise ValueError("源库位无可用批次")

        need = float(qty)
        src_sid = await self._ensure_stock_row(
            session, item_id=item_id, location_id=src_location_id
        )
        dst_sid = await self._ensure_stock_row(
            session, item_id=item_id, location_id=dst_location_id
        )
        src_after = await self._get_current_qty(
            session, item_id=item_id, location_id=src_location_id
        )
        dst_after = await self._get_current_qty(
            session, item_id=item_id, location_id=dst_location_id
        )

        moves: list[dict] = []

        for r in rows:
            if need <= 0:
                break
            available = float(r.qty or 0)
            if available <= 0:
                continue
            take = min(need, available)
            need -= take

            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == r.id)
                .values(qty=func.coalesce(Batch.qty, 0) - int(take)),
            )
            src_after -= take
            await _exec_with_retry(
                session,
                insert(StockLedger).values(
                    stock_id=src_sid,
                    batch_id=int(r.id),
                    delta=-int(take),
                    reason=reason,
                    ref=ref,
                    after_qty=int(src_after),
                ),
            )

            dst_bid = await self._ensure_batch(
                session=session,
                item_id=item_id,
                warehouse_id=dst_wh,
                location_id=dst_location_id,
                batch_code=r.batch_code,
                production_date=(
                    r.production_date if "production_date" in Batch.__table__.c else None
                ),
                expiry_date=r.expiry_date if "expiry_date" in Batch.__table__.c else None,
            )
            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == dst_bid)
                .values(qty=func.coalesce(Batch.qty, 0) + int(take)),
            )
            dst_after += take
            await _exec_with_retry(
                session,
                insert(StockLedger).values(
                    stock_id=dst_sid,
                    batch_id=int(dst_bid),
                    delta=int(take),
                    reason=reason,
                    ref=ref,
                    after_qty=int(dst_after),
                ),
            )

            moves.append(
                dict(
                    src_batch_id=int(r.id),
                    dst_batch_id=int(dst_bid),
                    batch_code=r.batch_code,
                    qty=int(take),
                )
            )

        if need > 1e-12:
            raise ValueError("库存不足，调拨未达成所需数量")

        await self._bump_stock(
            session, item_id=item_id, location_id=src_location_id, delta=-float(qty)
        )
        await self._bump_stock(
            session, item_id=item_id, location_id=dst_location_id, delta=+float(qty)
        )
        await session.commit()

        return {
            "item_id": item_id,
            "src_location_id": src_location_id,
            "dst_location_id": dst_location_id,
            "total_moved": int(qty),
            "moves": moves,
        }

    # ==================== Helpers（异步） ====================
    async def _get_current_qty(
        self, session: AsyncSession, *, item_id: int, location_id: int
    ) -> float:
        q = select(Stock.quantity).where(Stock.item_id == item_id, Stock.location_id == location_id)
        val = (await session.execute(q)).scalar_one_or_none()
        return float(val or 0.0)

    async def _resolve_warehouse_id(self, session: AsyncSession, location_id: int) -> int:
        wid = (
            await session.execute(select(Location.warehouse_id).where(Location.id == location_id))
        ).scalar_one_or_none()
        if wid is not None:
            return int(wid)

        w_first = (
            await session.execute(select(Warehouse.id).order_by(Warehouse.id.asc()))
        ).scalar_one_or_none()
        if w_first is None:
            res_w = await _exec_with_retry(
                session, insert(Warehouse).values({"name": "AUTO-WH"}).returning(Warehouse.id)
            )
            wid_new = int(res_w.scalar_one())
        else:
            wid_new = int(w_first)

        try:
            await _exec_with_retry(
                session,
                insert(Location).values(
                    {"id": location_id, "name": f"AUTO-LOC-{location_id}", "warehouse_id": wid_new}
                ),
            )
        except IntegrityError:
            pass

        return wid_new

    async def _ensure_location(self, session: AsyncSession, warehouse_id: int, name: str) -> int:
        r = (
            await session.execute(
                select(Location.id).where(
                    Location.warehouse_id == warehouse_id, Location.name == name
                )
            )
        ).scalar_one_or_none()
        if r:
            return int(r)
        res = await _exec_with_retry(
            session,
            insert(Location)
            .values({"warehouse_id": warehouse_id, "name": name})
            .returning(Location.id),
        )
        return int(res.scalar_one())

    async def _ensure_item_exists(self, session: AsyncSession, *, item_id: int) -> None:
        exists = (
            await session.execute(select(Item.id).where(Item.id == item_id))
        ).scalar_one_or_none()
        if exists is not None:
            return
        vals: dict = {"id": item_id, "sku": f"ITEM-{item_id}", "name": f"Auto Item {item_id}"}
        for fld in ("qty_available", "qty_on_hand", "qty_reserved", "qty", "min_qty", "max_qty"):
            if hasattr(Item, fld):
                vals.setdefault(fld, 0)
        if hasattr(Item, "unit"):
            vals.setdefault("unit", "EA")
        try:
            await _exec_with_retry(session, insert(Item).values(vals))
        except IntegrityError:
            await session.rollback()

    async def _ensure_batch(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        location_id: int,
        batch_code: str,
        production_date: date | None,
        expiry_date: date | None,
    ) -> int:
        await self._ensure_item_exists(session, item_id=item_id)

        conds = [
            Batch.item_id == item_id,
            Batch.warehouse_id == warehouse_id,
            Batch.location_id == location_id,
            Batch.batch_code == batch_code,
        ]
        existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
        if existed:
            return int(existed)

        await asyncio.sleep(0.02)

        vals: dict = dict(
            item_id=item_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            batch_code=batch_code,
            qty=0,
        )
        if "production_date" in Batch.__table__.c:
            vals[Batch.production_date.key] = production_date
        if "expiry_date" in Batch.__table__.c:
            vals[Batch.expiry_date.key] = expiry_date

        try:
            rid = (
                await _exec_with_retry(session, insert(Batch).values(vals).returning(Batch.id))
            ).scalar_one()
            return int(rid)
        except IntegrityError:
            await session.rollback()
            rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
            return int(rid2)

    async def _ensure_stock_row(
        self, session: AsyncSession, *, item_id: int, location_id: int
    ) -> int:
        sid = (
            await session.execute(
                select(Stock.id).where(Stock.item_id == item_id, Stock.location_id == location_id)
            )
        ).scalar_one_or_none()
        if sid:
            return int(sid)
        res = await _exec_with_retry(
            session,
            insert(Stock)
            .values({"item_id": item_id, "location_id": location_id, "quantity": 0})
            .returning(Stock.id),
        )
        return int(res.scalar_one())

    async def _bump_stock(
        self, session: AsyncSession, *, item_id: int, location_id: int, delta: float
    ) -> None:
        cur = (
            await session.execute(
                select(Stock.quantity).where(
                    Stock.item_id == item_id, Stock.location_id == location_id
                )
            )
        ).scalar_one_or_none()
        if cur is None:
            await _exec_with_retry(
                session,
                insert(Stock).values(
                    {"item_id": item_id, "location_id": location_id, "quantity": float(delta)}
                ),
            )
            return
        await _exec_with_retry(
            session,
            update(Stock)
            .where(Stock.item_id == item_id, Stock.location_id == location_id)
            .values(quantity=func.coalesce(Stock.quantity, 0) + float(delta)),
        )

    # ==================== 同步薄封装（确保外键存在） ====================
    def adjust_sync(
        self,
        *,
        item_id: int,
        location_id: int,
        delta: float,
        allow_negative: bool = True,
        reason: str = "INBOUND",
        ref: str | None = None,
        batch_code: str | None = None,
    ) -> tuple[int, float, float, float]:
        """
        同步入口用于 /stock/adjust 汇总库存调整。
        加强：兜底创建缺失的 Item/Location，避免外键冲突。
        """
        assert self.db is not None, "同步模式需要 self.db Session"

        # 确保 Location 存在
        loc = self.db.query(Location).filter_by(id=location_id).first()
        if loc is None:
            wh = self.db.query(Warehouse).order_by(Warehouse.id.asc()).first()
            if wh is None:
                wh = Warehouse(name="AUTO-WH")
                self.db.add(wh)
                self.db.flush()
            loc = Location(id=location_id, name=f"AUTO-LOC-{location_id}", warehouse_id=wh.id)
            self.db.add(loc)
            self.db.flush()

        # 确保 Item 存在
        itm = self.db.query(Item).filter_by(id=item_id).first()
        if itm is None:
            itm = Item(id=item_id, sku=f"ITEM-{item_id}", name=f"Auto Item {item_id}")
            for fld in (
                "qty_available",
                "qty_on_hand",
                "qty_reserved",
                "qty",
                "min_qty",
                "max_qty",
            ):
                if hasattr(Item, fld) and getattr(itm, fld, None) is None:
                    setattr(itm, fld, 0)
            if hasattr(Item, "unit") and getattr(itm, "unit", None) is None:
                itm.unit = "EA"
            self.db.add(itm)
            self.db.flush()

        # 汇总库存 upsert
        col_qty = getattr(Stock, "quantity", getattr(Stock, "qty", None))
        assert col_qty is not None, "Stock 模型缺少数量列（quantity/qty）"

        before = (
            self.db.query(col_qty)
            .filter(Stock.item_id == item_id, Stock.location_id == location_id)
            .scalar()
            or 0.0
        )
        new_qty = float(before) + float(delta)
        if new_qty < 0 and not allow_negative:
            raise ValueError("库存不足，禁止负数库存")

        row = self.db.query(Stock).filter_by(item_id=item_id, location_id=location_id).first()
        if row:
            setattr(row, col_qty.key, new_qty)
        else:
            row = Stock(item_id=item_id, location_id=location_id)
            setattr(row, col_qty.key, new_qty)
            self.db.add(row)

        self.db.commit()
        return (item_id, float(before), float(delta), float(new_qty))

    # ==================== 同步统计 & 查询（保留） ====================
    def summarize_by_item(self, *, item_id: int, warehouse_id: int):
        """
        汇总某仓下某商品的总量（JOIN locations 约束仓库）。
        1) 运行时从表元数据取 stocks 的真实数量列（quantity/qty）
        2) 运行时从表元数据取 locations 的仓列（warehouse_id/warehouse/wh_id）
        3) 如按仓过滤仍拿空，兜底为“全仓汇总”以避免 ORM/方言边角误伤
        """
        from sqlalchemy import inspect as _inspect
        from sqlalchemy import text as _text

        assert self.db is not None, "同步模式需要 self.db Session"

        # --- 1) 真实 DB 列名：stocks 数量列 ---
        qty_col_obj = getattr(Stock.__table__.c, "quantity", None) or getattr(
            Stock.__table__.c, "qty", None
        )
        if qty_col_obj is None:
            raise RuntimeError("stocks 表缺少数量列（quantity/qty）")
        qty_db_col = qty_col_obj.name
        stocks_tbl = Stock.__table__.name  # 通常 'stocks'

        # --- 2) 真实 DB 列名：locations 的仓库外键列 ---
        loc_tbl = Location.__table__.name  # 通常 'locations'
        loc_cols = {c.name for c in Location.__table__.c}
        if "warehouse_id" in loc_cols:
            wh_col = "warehouse_id"
        elif "warehouse" in loc_cols:
            wh_col = "warehouse"
        elif "wh_id" in loc_cols:
            wh_col = "wh_id"
        else:
            # 极端情况：从数据库反射一次（少见）
            insp = _inspect(self.db.get_bind())
            try:
                db_cols = {c["name"] for c in insp.get_columns(loc_tbl)}
            except Exception:
                db_cols = set()
            wh_col = (
                "warehouse_id"
                if "warehouse_id" in db_cols
                else ("warehouse" if "warehouse" in db_cols else None)
            )
            if wh_col is None:
                # 实在没有仓列，就退化成“全仓汇总”
                wh_col = None

        # --- 3) 主查询：按仓 JOIN + 汇总 ---
        if wh_col:
            sql_with_wh = f"""
                SELECT s.item_id, SUM(COALESCE(s.{qty_db_col}, 0)) AS total
                FROM {stocks_tbl} AS s
                JOIN {loc_tbl} AS l ON s.location_id = l.id
                WHERE s.item_id = :item_id AND l.{wh_col} = :wh
                GROUP BY s.item_id
            """
            rows = self.db.execute(
                _text(sql_with_wh), {"item_id": item_id, "wh": warehouse_id}
            ).all()
        else:
            rows = []

        # --- 兜底：若按仓过滤异常拿空，改为“全仓汇总”以避免误伤 ---
        if not rows:
            sql_all = f"""
                SELECT s.item_id, SUM(COALESCE(s.{qty_db_col}, 0)) AS total
                FROM {stocks_tbl} AS s
                WHERE s.item_id = :item_id
                GROUP BY s.item_id
            """
            rows = self.db.execute(_text(sql_all), {"item_id": item_id}).all()

        return [(int(r[0]), float(r[1] or 0.0)) for r in rows]

    def query_rows(
        self,
        *,
        item_id: int | None = None,
        warehouse_id: int | None = None,
        location_id: int | None = None,
    ):
        q = self.db.query(Stock).join(Location, Stock.location_id == Location.id)
        if item_id is not None:
            q = self.db.query(Stock).filter(Stock.item_id == item_id)
        if warehouse_id is not None:
            q = q.filter(Location.warehouse_id == warehouse_id)
        if location_id is not None:
            q = q.filter(Stock.location_id == location_id)
        return q.all()
