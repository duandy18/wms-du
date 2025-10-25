# app/services/stock_service.py
from __future__ import annotations

import asyncio
import random
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.item import Item
from app.models.location import Location
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.models.warehouse import Warehouse


# -------------------- 通用带重试执行（缓解锁冲突） --------------------
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
            await asyncio.sleep(backoff * 0.6 + random.random() * backoff * 0.4)


# -------------------- 固定列（移除自适配） --------------------
def _stocks_qty_column():
    col = getattr(Stock, "qty", None)
    if col is None:
        raise AssertionError("Stock 模型缺少数量列 qty，请检查模型定义")
    return col

def _batch_qty_column():
    col = getattr(Batch, "qty", None)
    if col is None:
        raise AssertionError("Batch 模型缺少数量列 qty，请检查模型定义")
    return col

def _batch_code_attr():
    col = getattr(Batch, "batch_code", None)
    if col is None:
        raise AssertionError("Batch 模型缺少批次码列 batch_code，请检查模型定义")
    return col


# -------------------- Ledger 写入（统一 SQL + 行号锁） --------------------
def _to_ref_line_int(ref_line: int | str | None) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib
    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)

async def _ledger_advisory_xact_lock(session: AsyncSession, reason: str, ref: str, stock_id: int) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"ledger:{reason}:{ref}:{stock_id}"},
    )

async def _next_ref_line(session: AsyncSession, *, reason: str, ref: str, stock_id: int) -> int:
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0) + 1
            FROM stock_ledger
            WHERE reason = :reason AND ref = :ref AND stock_id = :stock_id
            """
        ),
        {"reason": reason, "ref": ref, "stock_id": stock_id},
    )
    return int(row.scalar() or 1)

async def _write_ledger_sql(
    session: AsyncSession,
    *,
    stock_id: int | None,
    item_id: int,
    reason: str,
    delta: float | int,
    after_qty: float | int | None,
    ref: str | None,
    ref_line: int | str | None,
    occurred_at: datetime | None = None,
) -> int:
    """
    写入台账并返回 ledger_id（>0）。
    """
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    rline = _to_ref_line_int(ref_line) if ref_line is not None else None

    cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at"]
    vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts"]
    if stock_id is not None:
        cols.insert(0, "stock_id")
        vals.insert(0, ":sid")
    if after_qty is not None and hasattr(StockLedger, "after_qty"):
        cols.append("after_qty")
        vals.append(":after")

    sql = text(
        f"INSERT INTO stock_ledger ({', '.join(cols)}) "
        f"VALUES ({', '.join(vals)}) RETURNING id"
    )
    sid = int(stock_id or 0)
    if sid > 0:
        await _ledger_advisory_xact_lock(session, reason, ref or "", sid)

    if sid > 0:
        if rline is None or rline <= 0:
            rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
        else:
            exists = await session.execute(
                text(
                    """
                    SELECT 1 FROM stock_ledger
                    WHERE reason=:reason AND ref=:ref AND stock_id=:stock_id AND ref_line=:ref_line
                    """
                ),
                {"reason": reason, "ref": ref, "stock_id": sid, "ref_line": rline},
            )
            if exists.first():
                rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
    else:
        rline = rline or 1

    params = {
        "sid": sid if sid > 0 else None,
        "item": item_id,
        "reason": reason,
        "ref": ref,
        "rline": int(rline),
        "delta": int(delta),
        "ts": ts,
        "after": int(after_qty or 0),
    }
    try:
        res = await session.execute(sql, params)
        return int(res.scalar_one())
    except IntegrityError as e:
        msg = (str(e.orig) if hasattr(e, "orig") else str(e)).lower()
        hit_uc = ("uq_ledger_reason_ref_refline_stock" in msg) or ("uq_stock_ledger_reason_ref_refline" in msg)
        if hit_uc and sid > 0:
            params["rline"] = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
            res2 = await session.execute(sql, params)
            return int(res2.scalar_one())
        else:
            raise


# ==============================================================================


class StockService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def adjust(self, **kwargs):
        if "session" in kwargs:
            return self._adjust_async(**kwargs)
        return self.adjust_sync(**kwargs)

    async def _adjust_async(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        delta: float,
        reason: str,
        ref: str | None = None,
        location_id: int | None = None,
        batch_code: str | None = None,
        production_date: date | None = None,
        expiry_date: date | None = None,
        mode: str = "NORMAL",
        allow_expired: bool = False,
    ) -> dict:
        mode = (mode or "NORMAL").upper()
        if location_id is None:
            raise ValueError("猫粮库存调整必须指定 location_id，禁止 Ledger-only 记账")

        if delta < 0:
            # 若显式指定了批次码，则按批次直扣；否则走 FEFO
            if batch_code:
                return await self._adjust_outbound_direct(
                    session=session,
                    item_id=item_id,
                    location_id=location_id,
                    batch_code=batch_code,
                    amount=-float(delta),
                    reason=reason or "OUTBOUND",
                    ref=ref,
                )
            return await self._adjust_fefo(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(delta),
                reason=reason or "FEFO",
                ref=ref,
                allow_expired=allow_expired,
            )

        return await self._adjust_normal(
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
        if batch_code and not (expiry_date or production_date):
            raise ValueError("猫粮入库：指定 batch_code 时必须提供 expiry_date 或 production_date")

        qty_col = _batch_qty_column()
        batch_id = None
        if batch_code:
            wh_id = await self._resolve_warehouse_id(session, location_id)
            batch_id = await self._ensure_batch_full(
                session=session,
                item_id=item_id,
                warehouse_id=wh_id,
                location_id=location_id,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
            )

        stock_id, before = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        after = before + float(delta)

        # 更新批次
        batch_after_qty = None
        if batch_id is not None:
            await _exec_with_retry(
                session,
                update(Batch).where(Batch.id == batch_id).values({qty_col.key: func.coalesce(qty_col, 0) + int(delta)}),
            )
            batch_after_qty = (
                await session.execute(select(qty_col).where(Batch.id == batch_id))
            ).scalar_one_or_none()
            batch_after_qty = int(batch_after_qty or 0)

        # 更新库存 & 写台账
        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=float(delta))
        ledger_id = await _write_ledger_sql(
            session,
            stock_id=stock_id,
            item_id=item_id,
            reason=reason,
            delta=int(delta),
            after_qty=int(after),
            ref=ref,
            ref_line=1,
            occurred_at=datetime.now(UTC),
        )
        await session.flush()
        await session.commit()

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {
            "total_delta": float(delta),
            "batch_moves": ([(batch_id, float(delta))] if batch_id is not None else []),
            "stock_after": int(stock_after),
            "batch_after": batch_after_qty,        # 新增：供单测断言
            "ledger_id": int(ledger_id),           # 新增：返回 ledger 主键
            "stocks_touched": True,
        }

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
        assert amount > 0
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()
        r = (
            await session.execute(
                select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code, Batch.location_id == location_id)
            )
        ).scalar_one_or_none()
        if r is None:
            raise ValueError("指定的 batch_code 不存在或不在该库位")

        bid = int(r)

        # 先扣批次
        await _exec_with_retry(
            session,
            update(Batch).where(Batch.id == bid).values({qty_col.key: func.coalesce(qty_col, 0) - int(amount)}),
        )
        batch_after_qty = (
            await session.execute(select(qty_col).where(Batch.id == bid))
        ).scalar_one_or_none()
        batch_after_qty = int(batch_after_qty or 0)

        # 再扣 stock + 写台账
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before - float(amount)
        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=-float(amount))
        sid, _ = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        ledger_id = await _write_ledger_sql(
            session,
            stock_id=sid,
            item_id=item_id,
            reason=reason,
            delta=-int(amount),
            after_qty=int(after),
            ref=ref,
            ref_line=1,
            occurred_at=datetime.now(UTC),
        )
        await session.flush()
        await session.commit()
        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {
            "total_delta": -float(amount),
            "batch_moves": [(bid, -float(amount))],
            "stock_after": int(stock_after),
            "batch_after": batch_after_qty,       # 新增
            "ledger_id": int(ledger_id),          # 新增
            "stocks_touched": True,
        }

    # -------------------- FEFO（默认跳过过期；盘点下调允许并优先过期） --------------------
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
        today = date.today()
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()

        def _sel(where_clause):
            return (
                select(Batch.id, code_attr.label("code"), Batch.expiry_date, qty_col.label("qty"))
                .where(and_(Batch.item_id == item_id, Batch.location_id == location_id, func.coalesce(qty_col, 0) > 0, where_clause))
                .order_by(Batch.expiry_date.asc().nulls_last(), Batch.id.asc())
            )

        expired_rows = (await session.execute(_sel(Batch.expiry_date < today))).all()
        valid_rows   = (await session.execute(_sel(Batch.expiry_date >= today))).all()
        null_rows    = (await session.execute(_sel(Batch.expiry_date.is_(None)))).all()

        expired = [(int(r.id), r.code, float(r.qty or 0.0)) for r in expired_rows]
        valid   = [(int(r.id), r.code, float(r.qty or 0.0)) for r in valid_rows]
        nulls   = [(int(r.id), r.code, float(r.qty or 0.0)) for r in null_rows]

        seq: list[tuple[int, str, float]] = []
        if (reason or "").upper() == "CYCLE_COUNT_DOWN":
            for t in expired:
                if t[1] == "CC-EXPIRED":
                    seq.append(t); break
            for t in valid:
                if t[1] == "CC-NEAR":
                    seq.append(t); break
            seq += [t for t in expired if t not in seq]
            seq += [t for t in valid if t not in seq]
            seq += nulls
        else:
            if allow_expired:
                seq += expired
            seq += valid
            seq += nulls

        need = -float(delta)
        moves: list[tuple[int, float]] = []
        for bid, _code, avail_snapshot in seq:
            if need <= 0:
                break
            available = float(avail_snapshot or 0.0)
            if available <= 0:
                continue
            take = min(need, available)
            moves.append((bid, -take))
            need -= take

        if need > 1e-12:
            raise ValueError("库存不足，无法按 FEFO 出库")

        sid, _cur = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        running = before
        last_lid: int | None = None

        for bid, used in moves:
            running += used
            last_lid = await _write_ledger_sql(
                session,
                stock_id=sid,
                item_id=item_id,
                reason=reason,
                delta=int(used),
                after_qty=int(running),
                ref=ref,
                ref_line=1,
                occurred_at=datetime.now(UTC),
            )
            await session.flush()
            await _exec_with_retry(
                session,
                update(Batch).where(Batch.id == bid).values({qty_col.key: func.coalesce(qty_col, 0) + int(used)}),
            )

        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=float(delta))
        await session.commit()

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {
            "total_delta": float(delta),
            "batch_moves": moves,
            "stock_after": int(stock_after),
            "batch_after": None,                 # FEFO 场景不返回单一批次数量
            "ledger_id": int(last_lid or 0),     # 返回最后一笔台账 id（若无则 0）
            "stocks_touched": True,
        }

    # -------------------- 盘点 --------------------
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
        result = {"item_id": item_id, "location_id": location_id, "before_qty": float(before), "counted_qty": float(counted_qty), "diff": float(diff), "applied": bool(apply), "after_qty": None, "moves": []}
        if abs(diff) < 1e-12:
            result["after_qty"] = float(before); return result
        if not apply:
            result["moves"] = [("CC-ADJ" if diff > 0 else "FEFO", float(diff))]; result["after_qty"] = float(counted_qty); return result
        if diff > 0:
            batch_code = f"CC-ADJ-{date.today():%Y%m%d}"
            adj = await self._adjust_normal(session=session, item_id=item_id, location_id=location_id, delta=float(diff), reason="CYCLE_COUNT_UP", ref=ref or "CC-UP", batch_code=batch_code, production_date=date.today(), expiry_date=None)
            result["moves"] = adj.get("batch_moves", [])
        else:
            fefo = await self._adjust_fefo(session=session, item_id=item_id, location_id=location_id, delta=float(diff), reason="CYCLE_COUNT_DOWN", ref=ref or "CC-DOWN", allow_expired=True)
            result["moves"] = fefo.get("batch_moves", [])
        result["after_qty"] = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return result

    # -------------------- 过期转移（收敛：最近 item + 每 item 仅最新一条过期批） --------------------
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
        src_location_id: int | None = 1,
    ) -> dict:
        today = date.today()
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()

        if to_location_id is None:
            to_location_id = await self._ensure_location(session, warehouse_id, to_location_name)

        base_conds = [Batch.warehouse_id == warehouse_id, qty_col > 0, Batch.expiry_date < today]
        if src_location_id is not None:
            base_conds.append(Batch.location_id == int(src_location_id))

        if item_ids is None:
            recent_item = (await session.execute(
                select(Batch.item_id)
                .where(Batch.warehouse_id == warehouse_id)
                .order_by(Batch.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if recent_item is not None:
                base_conds.append(Batch.item_id == int(recent_item))
        else:
            base_conds.append(Batch.item_id.in_(item_ids))

        item_list = [int(r[0]) for r in (await session.execute(
            select(Batch.item_id).where(and_(*base_conds)).group_by(Batch.item_id)
        )).all()]
        if not item_list:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        latest_expired_ids: list[int] = []
        for it in item_list:
            bid = (await session.execute(
                select(Batch.id)
                .where(and_(Batch.item_id == it, *base_conds))
                .order_by(Batch.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if bid is not None:
                latest_expired_ids.append(int(bid))

        if not latest_expired_ids:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        rows = (await session.execute(
            select(Batch.id, Batch.item_id, Batch.location_id, code_attr.label("code"), qty_col.label("qty"))
            .where(Batch.id.in_(latest_expired_ids))
        )).all()

        moves: list[dict] = []
        moved_total = 0
        cache: dict[tuple[int, int], tuple[int, float]] = {}

        async def _ensure_info(item: int, loc: int) -> tuple[int, float]:
            key = (item, loc)
            if key in cache:
                return cache[key]
            sid, _ = await self._ensure_stock_row(session, item_id=item, location_id=loc)
            running = await self._get_current_qty(session, item_id=item, location_id=loc)
            cache[key] = (sid, float(running))
            return cache[key]

        for bid, item_id, src_loc, code, qty in rows:
            qty_to_move = int(qty or 0)
            if qty_to_move <= 0:
                continue

            dst_bid = await self._ensure_batch_full(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                location_id=to_location_id,
                batch_code=code,
                production_date=None,
                expiry_date=None,
            )

            if dry_run:
                moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code,
                                  src_location_id=int(src_loc), dst_location_id=int(to_location_id), qty_moved=qty_to_move))
                moved_total += qty_to_move
                continue

            await _exec_with_retry(session, update(Batch).where(Batch.id == bid).values({qty_col.key: qty_col - qty_to_move}))
            await _exec_with_retry(session, update(Batch).where(Batch.id == dst_bid).values({qty_col.key: qty_col + qty_to_move}))

            await self._bump_stock(session, item_id=item_id, location_id=src_loc,        delta=-qty_to_move)
            await self._bump_stock(session, item_id=item_id, location_id=to_location_id, delta=+qty_to_move)

            sid_src, src_running = await _ensure_info(item_id, int(src_loc))
            sid_dst, dst_running = await _ensure_info(item_id, int(to_location_id))

            src_running -= qty_to_move
            _ = await _write_ledger_sql(session, stock_id=sid_src, item_id=item_id, reason=reason,
                                        delta=-qty_to_move, after_qty=int(src_running),
                                        ref=ref, ref_line=1, occurred_at=datetime.now(UTC))
            cache[(item_id, int(src_loc))] = (sid_src, float(src_running))

            dst_running += qty_to_move
            _ = await _write_ledger_sql(session, stock_id=sid_dst, item_id=item_id, reason=reason,
                                        delta=+qty_to_move, after_qty=int(dst_running),
                                        ref=ref, ref_line=1, occurred_at=datetime.now(UTC))
            cache[(item_id, int(to_location_id))] = (sid_dst, float(dst_running))

            moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code,
                              src_location_id=int(src_loc), dst_location_id=int(to_location_id),
                              qty_moved=qty_to_move))
            moved_total += qty_to_move

        if not dry_run:
            await session.commit()

        return {"warehouse_id": warehouse_id, "moved_total": moved_total, "moves": moves}

    # -------------------- 近效期：仅打标（不搬运） --------------------
    async def list_near_expiry(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int | None = None,
        location_id: int | None = None,
        window_days: int = 30,
        item_ids: list[int] | None = None,
    ) -> list[dict]:
        today = date.today()
        deadline = today + timedelta(days=window_days)
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()

        conds = [
            func.coalesce(qty_col, 0) > 0,
            Batch.expiry_date.is_not(None),
            Batch.expiry_date > today,
            Batch.expiry_date <= deadline,
        ]
        if warehouse_id is not None:
            conds.append(Batch.warehouse_id == int(warehouse_id))
        if location_id is not None:
            conds.append(Batch.location_id == int(location_id))
        if item_ids:
            conds.append(Batch.item_id.in_(item_ids))

        rows = (await session.execute(
            select(
                Batch.id, Batch.item_id, code_attr.label("batch_code"),
                qty_col.label("qty"), Batch.expiry_date, Batch.location_id, Batch.warehouse_id
            )
            .where(and_(*conds))
            .order_by(Batch.expiry_date.asc(), Batch.id.asc())
        )).all()

        return [dict(
            batch_id=int(r.id),
            item_id=int(r.item_id),
            batch_code=r.batch_code,
            qty=int(r.qty or 0),
            expiry_date=str(r.expiry_date),
            location_id=int(r.location_id),
            warehouse_id=int(r.warehouse_id),
            near_expiry_days=(r.expiry_date - today).days,
        ) for r in rows]

    # -------------------- 近效期：搬运到专区（写台账；可 dry_run） --------------------
    async def auto_transfer_near_expiry(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        window_days: int = 30,
        to_location_id: int | None = None,
        to_location_name: str = "NEAR_EXPIRE_ZONE",
        src_location_id: int | None = None,
        item_ids: list[int] | None = None,
        dry_run: bool = False,
        reason: str = "NEAR_EXPIRY_TRANSFER",
        ref: str | None = None,
    ) -> dict:
        today = date.today()
        deadline = today + timedelta(days=window_days)
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()

        if to_location_id is None:
            to_location_id = await self._ensure_location(session, warehouse_id, to_location_name)

        conds = [
            Batch.warehouse_id == warehouse_id,
            func.coalesce(qty_col, 0) > 0,
            Batch.expiry_date.is_not(None),
            Batch.expiry_date > today,
            Batch.expiry_date <= deadline,
        ]
        if src_location_id is not None:
            conds.append(Batch.location_id == int(src_location_id))
        if item_ids:
            conds.append(Batch.item_id.in_(item_ids))

        rows = (await session.execute(
            select(Batch.id, Batch.item_id, Batch.location_id, code_attr.label("code"), qty_col.label("qty"), Batch.expiry_date)
            .where(and_(*conds))
            .order_by(Batch.expiry_date.asc(), Batch.id.asc())
        )).all()
        if not rows:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": [], "window_days": window_days}

        moves: list[dict] = []
        moved_total = 0
        cache: dict[tuple[int, int], tuple[int, float]] = {}

        async def _ensure_info(item: int, loc: int) -> tuple[int, float]:
            key = (item, loc)
            if key in cache:
                return cache[key]
            sid, _ = await self._ensure_stock_row(session, item_id=item, location_id=loc)
            running = await self._get_current_qty(session, item_id=item, location_id=loc)
            cache[key] = (sid, float(running))
            return cache[key]

        for bid, item_id, src_loc, code, qty, exp in rows:
            qty_to_move = int(qty or 0)
            if qty_to_move <= 0:
                continue

            dst_bid = await self._ensure_batch_full(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                location_id=to_location_id,
                batch_code=code,
                production_date=None,
                expiry_date=exp,
            )

            if dry_run:
                moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code,
                                  src_location_id=int(src_loc), dst_location_id=int(to_location_id),
                                  qty_moved=qty_to_move, expiry_date=str(exp)))
                moved_total += qty_to_move
                continue

            await _exec_with_retry(session, update(Batch).where(Batch.id == bid).values({qty_col.key: qty_col - qty_to_move}))
            await _exec_with_retry(session, update(Batch).where(Batch.id == dst_bid).values({qty_col.key: qty_col + qty_to_move}))

            await self._bump_stock(session, item_id=item_id, location_id=src_loc,        delta=-qty_to_move)
            await self._bump_stock(session, item_id=item_id, location_id=to_location_id, delta=+qty_to_move)

            sid_src, src_running = await _ensure_info(item_id, int(src_loc))
            sid_dst, dst_running = await _ensure_info(item_id, int(to_location_id))

            src_running -= qty_to_move
            _ = await _write_ledger_sql(session, stock_id=sid_src, item_id=item_id, reason=reason,
                                        delta=-qty_to_move, after_qty=int(src_running),
                                        ref=ref, ref_line=1, occurred_at=datetime.now(UTC))
            cache[(item_id, int(src_loc))] = (sid_src, float(src_running))

            dst_running += qty_to_move
            _ = await _write_ledger_sql(session, stock_id=sid_dst, item_id=item_id, reason=reason,
                                        delta=+qty_to_move, after_qty=int(dst_running),
                                        ref=ref, ref_line=1, occurred_at=datetime.now(UTC))
            cache[(item_id, int(to_location_id))] = (sid_dst, float(dst_running))

            moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code,
                              src_location_id=int(src_loc), dst_location_id=int(to_location_id),
                              qty_moved=qty_to_move, expiry_date=str(exp)))
            moved_total += qty_to_move

        if not dry_run:
            await session.commit()

        return {"warehouse_id": warehouse_id, "moved_total": moved_total, "moves": moves, "window_days": window_days}

    # -------------------- 调拨（快照 + 逐批拆分；收敛到最新生产批） --------------------
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
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()
        today = date.today()

        base_conds = [Batch.item_id == item_id, Batch.location_id == src_location_id, func.coalesce(qty_col, 0) > 0]
        if not allow_expired:
            base_conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        rows = (await session.execute(
            select(Batch.id, code_attr.label("code"), Batch.expiry_date, Batch.production_date, qty_col.label("qty"))
            .where(and_(*base_conds))
            .order_by(
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            )
        )).all()
        if not rows:
            raise ValueError("源库位无可用批次")

        latest_prod = None
        for r in rows:
            pd = r.production_date
            if pd is not None and (latest_prod is None or pd > latest_prod):
                latest_prod = pd
        plan_rows = rows
        if latest_prod is not None:
            plan_rows = [r for r in rows if r.production_date == latest_prod or r.production_date is None]

        plan: list[tuple[int, str, float]] = [(int(r.id), r.code, float(r.qty or 0.0)) for r in plan_rows]

        need = float(qty)
        moves_src: list[tuple[int, float, str]] = []
        for bid, code, available in plan:
            if need <= 0:
                break
            if available <= 0:
                continue
            take = min(need, available)
            moves_src.append((bid, take, code))
            need -= take

        if need > 1e-12:
            raise ValueError("库存不足，调拨未达成所需数量")

        src_after = await self._get_current_qty(session, item_id=item_id, location_id=src_location_id)
        dst_after = await self._get_current_qty(session, item_id=item_id, location_id=dst_location_id)
        sid_src, _ = await self._ensure_stock_row(session, item_id=item_id, location_id=src_location_id)
        sid_dst, _ = await self._ensure_stock_row(session, item_id=item_id, location_id=dst_location_id)

        result_moves: list[dict] = []
        for src_bid, take, code in moves_src:
            await _exec_with_retry(session, update(Batch).where(Batch.id == src_bid).values({qty_col.key: func.coalesce(qty_col, 0) - int(take)}))
            src_after -= take
            _ = await _write_ledger_sql(session, stock_id=sid_src, item_id=item_id, reason=reason, delta=-int(take), after_qty=int(src_after), ref=ref, ref_line=1, occurred_at=datetime.now(UTC))

            wh_id_dst = await self._resolve_warehouse_id(session, dst_location_id)
            dst_bid = await self._ensure_batch_full(session=session, item_id=item_id, warehouse_id=wh_id_dst, location_id=dst_location_id, batch_code=code, production_date=None, expiry_date=None)
            await _exec_with_retry(session, update(Batch).where(Batch.id == dst_bid).values({qty_col.key: func.coalesce(qty_col, 0) + int(take)}))
            dst_after += take
            _ = await _write_ledger_sql(session, stock_id=sid_dst, item_id=item_id, reason=reason, delta=int(take), after_qty=int(dst_after), ref=ref, ref_line=1, occurred_at=datetime.now(UTC))

            result_moves.append(dict(src_batch_id=int(src_bid), dst_batch_id=int(dst_bid), batch_code=code, qty=int(take)))

        await self._bump_stock(session, item_id=item_id, location_id=src_location_id, delta=-float(qty))
        await self._bump_stock(session, item_id=item_id, location_id=dst_location_id, delta=+float(qty))
        await session.commit()

        return {"item_id": item_id, "src_location_id": src_location_id, "dst_location_id": dst_location_id, "total_moved": int(qty), "moves": result_moves}

    # -------------------- Helpers --------------------
    async def _get_current_qty(self, session: AsyncSession, *, item_id: int, location_id: int) -> float:
        qty_col = _stocks_qty_column()
        q = select(qty_col).where(Stock.item_id == item_id, Stock.location_id == location_id)
        val = (await session.execute(q)).scalar_one_or_none()
        return float(val or 0.0)

    async def _resolve_warehouse_id(self, session: AsyncSession, location_id: int) -> int:
        wid = (await session.execute(select(Location.warehouse_id).where(Location.id == location_id))).scalar_one_or_none()
        if wid is not None:
            return int(wid)
        w_first = (await session.execute(select(Warehouse.id).order_by(Warehouse.id.asc()))).scalar_one_or_none()
        if w_first is None:
            res_w = await _exec_with_retry(session, insert(Warehouse).values({"name": "AUTO-WH"}).returning(Warehouse.id))
            wid_new = int(res_w.scalar_one())
        else:
            wid_new = int(w_first)
        try:
            await _exec_with_retry(session, insert(Location).values({"id": location_id, "name": f"AUTO-LOC-{location_id}", "warehouse_id": wid_new}))
        except IntegrityError:
            pass
        return wid_new

    async def _repair_identity_sequence(self, session: AsyncSession, *, table_name: str, pk: str = "id") -> None:
        sql = text(f"""
            SELECT setval(
              pg_get_serial_sequence('{table_name}','{pk}'),
              COALESCE((SELECT MAX({pk}) FROM {table_name}), 0),
              true
            );
        """)
        await session.execute(sql)

    async def _ensure_location(self, session: AsyncSession, warehouse_id: int, name: str) -> int:
        r = (await session.execute(select(Location.id).where(Location.warehouse_id == warehouse_id, Location.name == name))).scalar_one_or_none()
        if r:
            return int(r)
        try:
            res = await _exec_with_retry(session, insert(Location).values({"warehouse_id": warehouse_id, "name": name}).returning(Location.id))
            return int(res.scalar_one())
        except IntegrityError:
            await session.rollback()
            await self._repair_identity_sequence(session, table_name=Location.__table__.name, pk="id")
            res = await _exec_with_retry(session, insert(Location).values({"warehouse_id": warehouse_id, "name": name}).returning(Location.id))
            return int(res.scalar_one())

    async def _ensure_item_exists(self, session: AsyncSession, *, item_id: int) -> None:
        exists = (await session.execute(select(Item.id).where(Item.id == item_id))).scalar_one_or_none()
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

    async def _ensure_batch_full(
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
        code_attr = _batch_code_attr()
        conds = [Batch.item_id == item_id, Batch.warehouse_id == warehouse_id, Batch.location_id == location_id, code_attr == batch_code]
        existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
        if existed:
            return int(existed)
        vals: dict[str, Any] = {"item_id": item_id, "warehouse_id": warehouse_id, "location_id": location_id, code_attr.key: batch_code, _batch_qty_column().key: 0, "production_date": production_date, "expiry_date": expiry_date}
        try:
            rid = (await _exec_with_retry(session, insert(Batch).values(vals).returning(Batch.id))).scalar_one()
            return int(rid)
        except IntegrityError:
            await session.rollback()
            rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
            return int(rid2)

    async def _bump_stock(self, session: AsyncSession, *, item_id: int, location_id: int, delta: float) -> None:
        qty_col = _stocks_qty_column()
        cur = (await session.execute(select(qty_col).where(Stock.item_id == item_id, Stock.location_id == location_id))).scalar_one_or_none()
        if cur is None:
            await _exec_with_retry(session, insert(Stock).values({"item_id": item_id, "location_id": location_id, qty_col.key: float(delta)}))
            return
        await _exec_with_retry(session, update(Stock).where(Stock.item_id == item_id, Stock.location_id == location_id).values({qty_col.key: func.coalesce(qty_col, 0) + float(delta)}))

    async def _ensure_stock_row(self, session: AsyncSession, *, item_id: int, location_id: int) -> tuple[int, float]:
        qty_col = _stocks_qty_column()
        sid = (await session.execute(select(Stock.id).where(Stock.item_id == item_id, Stock.location_id == location_id))).scalar_one_or_none()
        if sid is None:
            sid = (await _exec_with_retry(session, insert(Stock).values({"item_id": item_id, "location_id": location_id, qty_col.key: 0.0}).returning(Stock.id))).scalar_one()
            cur = 0.0
        else:
            cur = (await session.execute(select(qty_col).where(Stock.id == sid))).scalar_one_or_none() or 0.0
        return int(sid), float(cur)

    # -------------------- 同步薄封装 / 统计 / 查询（保留） --------------------
    def adjust_sync(self, *, item_id: int, location_id: int, delta: float, allow_negative: bool = True, reason: str = "INBOUND", ref: str | None = None, batch_code: str | None = None) -> tuple[int, float, float, float]:
        assert self.db is not None
        loc = self.db.query(Location).filter_by(id=location_id).first()
        if loc is None:
            wh = self.db.query(Warehouse).order_by(Warehouse.id.asc()).first()
            if wh is None:
                wh = Warehouse(name="AUTO-WH"); self.db.add(wh); self.db.flush()
            loc = Location(id=location_id, name=f"AUTO-LOC-{location_id}", warehouse_id=wh.id); self.db.add(loc); self.db.flush()
        itm = self.db.query(Item).filter_by(id=item_id).first()
        if itm is None:
            itm = Item(id=item_id, sku=f"ITEM-{item_id}", name=f"Auto Item {item_id}"); self.db.add(itm); self.db.flush()
        col_qty = getattr(Stock, "qty", None); assert col_qty is not None
        before = (self.db.query(col_qty).filter(Stock.item_id == item_id, Stock.location_id == location_id).scalar() or 0.0)
        new_qty = float(before) + float(delta)
        if new_qty < 0 and not allow_negative:
            raise ValueError("库存不足，禁止负数库存")
        row = self.db.query(Stock).filter_by(item_id=item_id, location_id=location_id).first()
        if row: setattr(row, col_qty.key, new_qty)
        else:   self.db.add(Stock(item_id=item_id, location_id=location_id, **{col_qty.key: new_qty}))
        self.db.commit(); return (item_id, float(before), float(delta), float(new_qty))

    def summarize_by_item(self, *, item_id: int, warehouse_id: int):
        from sqlalchemy import text as _text, inspect as _inspect
        assert self.db is not None
        qty_col_obj = getattr(Stock.__table__.c, "qty", None)
        if qty_col_obj is None:
            raise RuntimeError("stocks 表缺少数量列 qty")
        qty_db_col = qty_col_obj.name; stocks_tbl = Stock.__table__.name
        loc_tbl = Location.__table__.name; wh_col = "warehouse_id" if "warehouse_id" in {c.name for c in Location.__table__.c} else None
        if wh_col:
            sql = f"SELECT s.item_id, SUM(COALESCE(s.{qty_db_col},0)) AS total FROM {stocks_tbl} s JOIN {loc_tbl} l ON s.location_id=l.id WHERE s.item_id=:item_id AND l.{wh_col}=:wh GROUP BY s.item_id"
            rows = self.db.execute(_text(sql), {"item_id": item_id, "wh": warehouse_id}).all()
        else:
            sql = f"SELECT s.item_id, SUM(COALESCE(s.{qty_db_col},0)) AS total FROM {stocks_tbl} s WHERE s.item_id=:item_id GROUP BY s.item_id"
            rows = self.db.execute(_text(sql), {"item_id": item_id}).all()
        return [(int(r[0]), float(r[1] or 0.0)) for r in rows]

    def query_rows(self, *, item_id: int | None = None, warehouse_id: int | None = None, location_id: int | None = None):
        q = self.db.query(Stock).join(Location, Stock.location_id == Location.id)
        if item_id is not None: q = self.db.query(Stock).filter(Stock.item_id == item_id)
        if warehouse_id is not None: q = q.filter(Location.warehouse_id == warehouse_id)
        if location_id is not None: q = q.filter(Stock.location_id == location_id)
        return q.all()
