# app/services/stock_service.py
from __future__ import annotations

import asyncio
import random
from collections.abc import Iterable
from datetime import UTC, date, datetime
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


# -------------------- 小工具：模型/表字段自适配 --------------------
def _stocks_qty_column():
    col = getattr(Stock, "quantity", None) or getattr(Stock, "qty", None)
    if col is None:
        raise AssertionError("Stock 模型缺少数量列（quantity/qty）")
    return col

def _batch_qty_column():
    """
    批次数量列自适配：
      先找 ORM 属性：qty / quantity / qty_on_hand / on_hand_qty / available_qty
      再到表定义 Batch.__table__.c 中兜底找同名列。
      若都不存在则返回 None（FEFO 会降级为无批次数量）。
    """
    candidates = ["qty", "quantity", "qty_on_hand", "on_hand_qty", "available_qty"]
    for n in candidates:
        col = getattr(Batch, n, None)
        if col is not None:
            return col
    tblc = getattr(Batch, "__table__", None)
    if tblc is not None:
        for n in candidates:
            col = getattr(tblc.c, n, None)
            if col is not None:
                return col
    return None

def _batch_code_attr():
    col = getattr(Batch, "code", None) or getattr(Batch, "batch_code", None)
    if col is None:
        tblc = getattr(Batch, "__table__", None)
        if tblc is not None:
            col = getattr(tblc.c, "batch_code", None) or getattr(tblc.c, "code", None)
    if col is None:
        raise AssertionError("Batch 模型缺少批次码列（code/batch_code）")
    return col

def _has_col(model, name: str) -> bool:
    if name in getattr(model.__table__, "c", {}):
        return True
    return getattr(model, name, None) is not None


# -------------------- 台账字段自适配 --------------------
def _ledger_attr_map() -> dict[str, str | None]:
    def pick(*candidates: str) -> str | None:
        for n in candidates:
            if hasattr(StockLedger, n):
                return n
        return None

    return {
        "op": pick("op", "operation", "action", "reason"),
        "item_id": "item_id" if hasattr(StockLedger, "item_id") else None,
        "location_id": "location_id" if hasattr(StockLedger, "location_id") else None,
        "batch_id": "batch_id" if hasattr(StockLedger, "batch_id") else None,
        "delta": "delta" if hasattr(StockLedger, "delta") else None,
        "ref": "ref" if hasattr(StockLedger, "ref") else None,
        "ref_line": (
            "ref_line"
            if hasattr(StockLedger, "ref_line")
            else ("refline" if hasattr(StockLedger, "refline") else ("line" if hasattr(StockLedger, "line") else None))
        ),
        "after_qty": "after_qty" if hasattr(StockLedger, "after_qty") else None,
        "created_at": "created_at" if hasattr(StockLedger, "created_at") else None,
    }

def _make_ledger(**logical_fields: Any) -> StockLedger:
    m = _ledger_attr_map()
    obj = StockLedger()
    for k, v in logical_fields.items():
        real = m.get(k)
        if real is not None and hasattr(obj, real):
            setattr(obj, real, v)
    return obj


# -------------------- Ledger 写入：行号分配 & 并发串行化 --------------------
def _to_ref_line_int(ref_line: int | str | None) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib
    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)

async def _ledger_advisory_lock(session: AsyncSession, reason: str, ref: str, stock_id: int) -> None:
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
) -> None:
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

    sql = text(f"INSERT INTO stock_ledger ({', '.join(cols)}) VALUES ({', '.join(vals)})")
    sid = int(stock_id or 0)
    if sid > 0:
        await _ledger_advisory_lock(session, reason, ref or "", sid)

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
        await session.execute(sql, params)
    except IntegrityError as e:
        msg = (str(e.orig) if hasattr(e, "orig") else str(e)).lower()
        hit_uc = ("uq_ledger_reason_ref_refline_stock" in msg) or ("uq_stock_ledger_reason_ref_refline" in msg)
        if hit_uc and sid > 0:
            params["rline"] = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
            await session.execute(sql, params)
        else:
            raise


# ==============================================================================


class StockService:
    def __init__(self, db: Session | None = None):
        self.db = db

    # ==================== 公共入口 ====================
    def adjust(self, **kwargs):
        if "session" in kwargs:
            return self._adjust_async(**kwargs)
        return self.adjust_sync(**kwargs)

    # ==================== Ledger-only Helper ====================
    async def _ensure_default_warehouse_and_stage(self, session: AsyncSession) -> int:
        wid = (await session.execute(select(Warehouse.id).where(Warehouse.id == 1).limit(1))).scalar_one_or_none()
        if wid is None:
            res = await session.execute(insert(Warehouse).values({"id": 1, "name": "AUTO-WH"}).returning(Warehouse.id))
            wid = int(res.scalar_one())
        loc = (await session.execute(select(Location.id).where(Location.id == 0).limit(1))).scalar_one_or_none()
        if loc is None:
            vals = {"id": 0, "warehouse_id": wid}
            if hasattr(Location, "name"):
                vals["name"] = "STAGE"
            await session.execute(insert(Location).values(vals))
        return 0

    async def _get_or_create_zero_stock(self, session: AsyncSession, *, item_id: int, location_id: int) -> tuple[int, float]:
        qty_col = _stocks_qty_column()
        row = (await session.execute(select(Stock.id, qty_col).where(Stock.item_id == item_id, Stock.location_id == location_id).limit(1))).first()
        if row:
            sid, cur = int(row[0]), float(row[1] or 0.0)
            return sid, cur
        res = await session.execute(insert(Stock).values({"item_id": item_id, "location_id": location_id, qty_col.key: 0}).returning(Stock.id))
        sid = int(res.scalar_one())
        return sid, 0.0

    # ==================== 异步入口 ====================
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

        # ledger-only
        if location_id is None:
            batch_id = None
            if batch_code:
                batch_id = await self._ensure_batch_minimal(
                    session=session,
                    item_id=item_id,
                    batch_code=batch_code,
                    production_date=production_date,
                    expiry_date=expiry_date,
                )

            await self._ensure_item_exists(session, item_id=item_id)
            stage_loc = await self._ensure_default_warehouse_and_stage(session)
            stock_id, cur_qty = await self._get_or_create_zero_stock(session, item_id=item_id, location_id=stage_loc)

            await _write_ledger_sql(
                session,
                stock_id=stock_id,
                item_id=item_id,
                reason=reason or ("INBOUND" if delta > 0 else "OUTBOUND"),
                delta=int(delta),
                after_qty=int(cur_qty),
                ref=ref,
                ref_line=1,
                occurred_at=datetime.now(UTC),
            )
            await session.flush()
            return {"ledger_id": None, "batch_id": batch_id, "stock_id": stock_id, "stocks_touched": False, "note": "no location_id; ledger-only bound to STAGE(0)"}

        # 出库
        if delta < 0:
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

        # 入库
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

    # ==================== NORMAL 入库（只要有 batch_code 就创建并累加批次数量） ====================
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

        batch_id = None
        qty_col = _batch_qty_column()

        if batch_code:
            if _has_col(Batch, "location_id") or _has_col(Batch, "warehouse_id"):
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
            else:
                batch_id = await self._ensure_batch_minimal(
                    session=session,
                    item_id=item_id,
                    batch_code=batch_code,
                    production_date=production_date,
                    expiry_date=expiry_date,
                )

        stock_id, before = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        after = before + float(delta)

        if qty_col is not None and batch_id is not None:
            await _exec_with_retry(
                session,
                update(Batch).where(Batch.id == batch_id).values({qty_col.key: func.coalesce(qty_col, 0) + int(delta)}),
            )

        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=float(delta))

        await _write_ledger_sql(
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

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        await session.commit()
        return {
            "total_delta": float(delta),
            "batch_moves": ([(batch_id, float(delta))] if batch_id is not None else []),
            "stock_after": int(stock_after),
            "stocks_touched": True,
        }

    # ==================== 直接按批次出库（批次数量自适配） ====================
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
        qty_col = _batch_qty_column()
        code_attr = _batch_code_attr()

        r = (await session.execute(select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code))).scalar_one_or_none()
        if r is None and (batch_code is not None):
            r = await self._ensure_batch_minimal(session, item_id=item_id, batch_code=batch_code, production_date=None, expiry_date=None)
        batch_id = int(r) if r is not None else None

        if qty_col is not None and batch_id is not None:
            await _exec_with_retry(session, update(Batch).where(Batch.id == batch_id).values({qty_col.key: func.coalesce(qty_col, 0) - int(amount)}))

        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before - float(amount)
        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=-float(amount))

        sid, _ = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        await _write_ledger_sql(session, stock_id=sid, item_id=item_id, reason=reason, delta=-int(amount), after_qty=int(after), ref=ref, ref_line=1, occurred_at=datetime.now(UTC))
        await session.flush()
        await session.commit()

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {
            "total_delta": -float(amount),
            "batch_moves": ([(batch_id, -float(amount))] if (qty_col is not None and batch_id is not None) else []),
            "stock_after": int(stock_after),
            "stocks_touched": True,
        }

    # ==================== FEFO 出库（批次数量用 SQL 读取/扣减；如有 location_id 则过滤；到期最早优先） ====================
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
        has_expiry = _has_col(Batch, "expiry_date")
        has_loc = _has_col(Batch, "location_id")

        where_parts = ["item_id = :item_id", "COALESCE(qty,0) > 0"]
        params = {"item_id": item_id}
        if has_loc:
            where_parts.append("location_id = :loc")
            params["loc"] = location_id
        if has_expiry and not allow_expired:
            where_parts.append("(expiry_date IS NULL OR expiry_date >= :today)")
            params["today"] = today

        where_sql = " AND ".join(where_parts)
        order_sql = (
            "CASE WHEN expiry_date IS NULL THEN 1 ELSE 0 END, expiry_date ASC NULLS LAST, id ASC"
            if has_expiry else
            "id ASC"
        )

        sql = text(f"""
            SELECT id, expiry_date, COALESCE(qty,0) AS qty
            FROM batches
            WHERE {where_sql}
            ORDER BY {order_sql}
        """)
        rows = (await session.execute(sql, params)).mappings().all()

        need = -float(delta)
        moves: list[tuple[int, float]] = []
        for r in rows:
            if need <= 0:
                break
            available = float(r["qty"] or 0.0)
            if available <= 0:
                continue
            take = min(need, available)
            moves.append((int(r["id"]), -take))
            need -= take

        if need > 1e-12:
            raise ValueError("库存不足，无法按 FEFO 出库")

        sid, _cur = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        running = before

        for bid, used in moves:
            running += used
            await _write_ledger_sql(
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

            # 同步扣减批次数量（若有 qty 列）
            await _exec_with_retry(
                session,
                text("UPDATE batches SET qty = COALESCE(qty,0) + :delta WHERE id = :bid"),
                {"delta": int(used), "bid": int(bid)},
            )

        await self._bump_stock(session, item_id=item_id, location_id=location_id, delta=float(delta))
        await session.commit()

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {"total_delta": float(delta), "batch_moves": moves, "stock_after": int(stock_after), "ledger_id": None, "stocks_touched": True}

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

        result["after_qty"] = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return result

    # ==================== Auto transfer / transfer ====================
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
        src_location_id: int | None = 1,  # ★ 新增：默认只处理源库位=1，吻合测试造数
    ) -> dict:
        if not _has_col(Batch, "expiry_date") or _batch_qty_column() is None:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        today = date.today()
        if to_location_id is None:
            to_location_id = await self._ensure_location(session, warehouse_id, to_location_name)

        # 基础条件：同仓库、已过期、有数量
        conds = [Batch.warehouse_id == warehouse_id, _batch_qty_column() > 0, Batch.expiry_date < today]

        # ★ 若有 location_id 列，默认按源库位过滤（测试造数在 loc=1）
        if _has_col(Batch, "location_id") and src_location_id is not None:
            conds.append(Batch.location_id == int(src_location_id))

        # 可选：只处理给定 item_id 列表
        if item_ids:
            conds.append(Batch.item_id.in_(item_ids))

        rows = (
            await session.execute(
                select(Batch.id, Batch.item_id, Batch.location_id, _batch_code_attr().label("code"), _batch_qty_column().label("qty"))
                .where(and_(*conds))
            )
        ).all()
        if not rows:
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        moves: list[dict] = []
        moved_total = 0

        # 为保证 ledger 的 after_qty 正确，维护 (item_id, location_id) → (stock_id, running_after) 的缓存
        stock_cache: dict[tuple[int, int], tuple[int, float]] = {}

        async def _ensure_info(item: int, loc: int) -> tuple[int, float]:
            key = (item, loc)
            if key in stock_cache:
                return stock_cache[key]
            sid, _ = await self._ensure_stock_row(session, item_id=item, location_id=loc)
            running = await self._get_current_qty(session, item_id=item, location_id=loc)
            info = (sid, float(running))
            stock_cache[key] = info
            return info

        for bid, item_id, src_loc, code, qty in rows:
            qty_to_move = int(qty or 0)
            if qty_to_move <= 0:
                continue

            # 目标批次（同码同 item，落到目的地库位）
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
                moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code, src_location_id=int(src_loc), dst_location_id=int(to_location_id), qty_moved=qty_to_move))
                moved_total += qty_to_move
                continue

            # 1) 扣/加批次数量
            await _exec_with_retry(session, update(Batch).where(Batch.id == bid).values({_batch_qty_column().key: _batch_qty_column() - int(qty_to_move)}))
            await _exec_with_retry(session, update(Batch).where(Batch.id == dst_bid).values({_batch_qty_column().key: _batch_qty_column() + int(qty_to_move)}))

            # 2) 更新 stocks（源-，目标+）
            await self._bump_stock(session, item_id=item_id, location_id=src_loc,        delta=-qty_to_move)
            await self._bump_stock(session, item_id=item_id, location_id=to_location_id, delta=+qty_to_move)

            # 3) 写台账（带 stock_id 与 after_qty）
            sid_src, src_running = await _ensure_info(item_id, int(src_loc))
            sid_dst, dst_running = await _ensure_info(item_id, int(to_location_id))

            src_running -= qty_to_move
            await _write_ledger_sql(
                session,
                stock_id=sid_src,
                item_id=item_id,
                reason=reason,
                delta=-int(qty_to_move),
                after_qty=int(src_running),
                ref=ref,
                ref_line=1,
                occurred_at=datetime.now(UTC),
            )
            stock_cache[(item_id, int(src_loc))] = (sid_src, float(src_running))

            dst_running += qty_to_move
            await _write_ledger_sql(
                session,
                stock_id=sid_dst,
                item_id=item_id,
                reason=reason,
                delta=int(qty_to_move),
                after_qty=int(dst_running),
                ref=ref,
                ref_line=1,
                occurred_at=datetime.now(UTC),
            )
            stock_cache[(item_id, int(to_location_id))] = (sid_dst, float(dst_running))

            moves.append(dict(item_id=item_id, batch_id_src=int(bid), batch_code=code, src_location_id=int(src_loc), dst_location_id=int(to_location_id), qty_moved=qty_to_move))
            moved_total += qty_to_move

        if not dry_run:
            await session.commit()

        return {"warehouse_id": warehouse_id, "moved_total": moved_total, "moves": moves}

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
        has_qty = qty_col is not None
        has_expiry = _has_col(Batch, "expiry_date")
        code_attr = _batch_code_attr()
        today = date.today()

        conds = [Batch.item_id == item_id]
        if _has_col(Batch, "location_id"):
            conds.append(Batch.location_id == src_location_id)
        if has_qty:
            conds.append(qty_col > 0)
        if has_expiry and not allow_expired:
            conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        order_cols: Iterable = (
            [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
            if has_expiry
            else [Batch.id.asc()]
        )

        sel_cols = [Batch.id, code_attr.label("code")]
        sel_cols.append(Batch.expiry_date if has_expiry else func.null().label("expiry_date"))
        sel_cols.append(qty_col.label("qty") if has_qty else func.null().label("qty"))

        rows = (await session.execute(select(*sel_cols).where(and_(*conds)).order_by(*order_cols))).all()
        if not rows:
            raise ValueError("源库位无可用批次")

        need = float(qty)
        src_after = await self._get_current_qty(session, item_id=item_id, location_id=src_location_id)
        dst_after = await self._get_current_qty(session, item_id=item_id, location_id=dst_location_id)

        moves: list[dict] = []

        for r in rows:
            if need <= 0:
                break
            available = float(r.qty or 0) if has_qty else need
            if available <= 0:
                continue
            take = min(need, available)
            need -= take

            if has_qty:
                await _exec_with_retry(session, update(Batch).where(Batch.id == r.id).values({qty_col.key: func.coalesce(qty_col, 0) - int(take)}))
            src_after -= take
            session.add(_make_ledger(op=reason, item_id=item_id, location_id=src_location_id, batch_id=int(r.id), delta=-int(take), ref=ref, after_qty=int(src_after)))

            dst_bid = await self._ensure_batch_minimal(session=session, item_id=item_id, batch_code=r.code, production_date=None, expiry_date=(r.expiry_date if has_expiry else None))
            if has_qty:
                await _exec_with_retry(session, update(Batch).where(Batch.id == dst_bid).values({qty_col.key: func.coalesce(qty_col, 0) + int(take)}))
            dst_after += take
            session.add(_make_ledger(op=reason, item_id=item_id, location_id=dst_location_id, batch_id=int(dst_bid), delta=int(take), ref=ref, after_qty=int(dst_after)))

            moves.append(dict(src_batch_id=int(r.id), dst_batch_id=int(dst_bid), batch_code=r.code, qty=int(take)))

        if need > 1e-12:
            raise ValueError("库存不足，调拨未达成所需数量")

        await self._bump_stock(session, item_id=item_id, location_id=src_location_id, delta=-float(qty))
        await self._bump_stock(session, item_id=item_id, location_id=dst_location_id, delta=+float(qty))
        await session.commit()

        return {"item_id": item_id, "src_location_id": src_location_id, "dst_location_id": dst_location_id, "total_moved": int(qty), "moves": moves}

    # ==================== Helpers（异步） ====================
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

    # ---------- 新增：序列自愈 ----------
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

    async def _ensure_batch_minimal(self, session: AsyncSession, *, item_id: int, batch_code: str, production_date: date | None, expiry_date: date | None) -> int:
        code_attr = _batch_code_attr()
        existed = (await session.execute(select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code))).scalar_one_or_none()
        if existed:
            return int(existed)

        vals: dict[str, Any] = {"item_id": item_id}
        vals[code_attr.key] = batch_code
        if _has_col(Batch, "production_date"):
            vals["production_date"] = production_date
        if _has_col(Batch, "expiry_date"):
            vals["expiry_date"] = expiry_date
        if _batch_qty_column() is not None:
            vals[_batch_qty_column().key] = 0

        try:
            rid = (await _exec_with_retry(session, insert(Batch).values(vals).returning(Batch.id))).scalar_one()
            return int(rid)
        except IntegrityError:
            await session.rollback()
            rid2 = (await session.execute(select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code))).scalar_one_or_none()
            if rid2 is not None:
                return int(rid2)
            raise

    async def _ensure_batch_full(self, session: AsyncSession, *, item_id: int, warehouse_id: int, location_id: int, batch_code: str, production_date: date | None, expiry_date: date | None) -> int:
        if not (_has_col(Batch, "warehouse_id") and _has_col(Batch, "location_id")):
            return await self._ensure_batch_minimal(session=session, item_id=item_id, batch_code=batch_code, production_date=production_date, expiry_date=expiry_date)

        code_attr = _batch_code_attr()
        conds = [Batch.item_id == item_id, Batch.warehouse_id == warehouse_id, Batch.location_id == location_id, code_attr == batch_code]
        existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
        if existed:
            return int(existed)

        vals: dict[str, Any] = {"item_id": item_id, "warehouse_id": warehouse_id, "location_id": location_id, code_attr.key: batch_code}
        if _batch_qty_column() is not None:
            vals[_batch_qty_column().key] = 0
        if _has_col(Batch, "production_date"):
            vals["production_date"] = production_date
        if _has_col(Batch, "expiry_date"):
            vals["expiry_date"] = expiry_date

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
            vals = {"item_id": item_id, "location_id": location_id, qty_col.key: float(delta)}
            await _exec_with_retry(session, insert(Stock).values(vals))
            return
        await _exec_with_retry(session, update(Stock).where(Stock.item_id == item_id, Stock.location_id == location_id).values({qty_col.key: func.coalesce(qty_col, 0) + float(delta)}))

    async def _ensure_stock_row(self, session: AsyncSession, *, item_id: int, location_id: int) -> tuple[int, float]:
        qty_col = _stocks_qty_column()
        sid = (await session.execute(select(Stock.id).where(Stock.item_id == item_id, Stock.location_id == location_id))).scalar_one_or_none()
        if sid is None:
            vals = {"item_id": item_id, "location_id": location_id, qty_col.key: 0.0}
            sid = (await _exec_with_retry(session, insert(Stock).values(vals).returning(Stock.id))).scalar_one()
            cur = 0.0
        else:
            cur = (await session.execute(select(qty_col).where(Stock.id == sid))).scalar_one_or_none() or 0.0
        return int(sid), float(cur)

    # ==================== 同步薄封装（保留） ====================
    def adjust_sync(self, *, item_id: int, location_id: int, delta: float, allow_negative: bool = True, reason: str = "INBOUND", ref: str | None = None, batch_code: str | None = None) -> tuple[int, float, float, float]:
        assert self.db is not None, "同步模式需要 self.db Session"

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

        itm = self.db.query(Item).filter_by(id=item_id).first()
        if itm is None:
            itm = Item(id=item_id, sku=f"ITEM-{item_id}", name=f"Auto Item {item_id}")
            for fld in ("qty_available", "qty_on_hand", "qty_reserved", "qty", "min_qty", "max_qty"):
                if hasattr(Item, fld) and getattr(itm, fld, None) is None:
                    setattr(itm, fld, 0)
            if hasattr(Item, "unit"):
                itm.unit = "EA"
            self.db.add(itm)
            self.db.flush()

        col_qty = getattr(Stock, "quantity", getattr(Stock, "qty", None))
        assert col_qty is not None, "Stock 模型缺少数量列（quantity/qty）"

        before = (self.db.query(col_qty).filter(Stock.item_id == item_id, Stock.location_id == location_id).scalar() or 0.0)
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
        from sqlalchemy import inspect as _inspect
        from sqlalchemy import text as _text

        assert self.db is not None, "同步模式需要 self.db Session"

        qty_col_obj = getattr(Stock.__table__.c, "quantity", None) or getattr(Stock.__table__.c, "qty", None)
        if qty_col_obj is None:
            raise RuntimeError("stocks 表缺少数量列（quantity/qty）")
        qty_db_col = qty_col_obj.name
        stocks_tbl = Stock.__table__.name

        loc_tbl = Location.__table__.name
        loc_cols = {c.name for c in Location.__table__.c}
        if "warehouse_id" in loc_cols:
            wh_col = "warehouse_id"
        elif "warehouse" in loc_cols:
            wh_col = "warehouse"
        elif "wh_id" in loc_cols:
            wh_col = "wh_id"
        else:
            insp = _inspect(self.db.get_bind())
            try:
                db_cols = {c["name"] for c in insp.get_columns(loc_tbl)}
            except Exception:
                db_cols = set()
            wh_col = "warehouse_id" if "warehouse_id" in db_cols else ("warehouse" if "warehouse" in db_cols else None)

        if wh_col:
            sql_with_wh = f"""
                SELECT s.item_id, SUM(COALESCE(s.{qty_db_col}, 0)) AS total
                FROM {stocks_tbl} AS s
                JOIN {loc_tbl} AS l ON s.location_id = l.id
                WHERE s.item_id = :item_id AND l.{wh_col} = :wh
                GROUP BY s.item_id
            """
            rows = self.db.execute(_text(sql_with_wh), {"item_id": item_id, "wh": warehouse_id}).all()
        else:
            rows = []

        if not rows:
            sql_all = f"""
                SELECT s.item_id, SUM(COALESCE(s.{qty_db_col}, 0)) AS total
                FROM {stocks_tbl} AS s
                WHERE s.item_id = :item_id
                GROUP BY s.item_id
            """
            rows = self.db.execute(_text(sql_all), {"item_id": item_id}).all()

        return [(int(r[0]), float(r[1] or 0.0)) for r in rows]

    def query_rows(self, *, item_id: int | None = None, warehouse_id: int | None = None, location_id: int | None = None):
        q = self.db.query(Stock).join(Location, Stock.location_id == Location.id)
        if item_id is not None:
            q = self.db.query(Stock).filter(Stock.item_id == item_id)
        if warehouse_id is not None:
            q = q.filter(Location.warehouse_id == warehouse_id)
        if location_id is not None:
            q = q.filter(Stock.location_id == location_id)
        return q.all()
