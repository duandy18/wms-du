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
            await asyncio.sleep(backoff * (0.6 + random.random() * 0.4))


# -------------------- 小工具：模型特性探测 --------------------
def _stocks_qty_column():
    col = getattr(Stock, "quantity", None) or getattr(Stock, "qty", None)
    if col is None:
        raise AssertionError("Stock 模型缺少数量列（quantity/qty）")
    return col


def _batch_code_attr():
    col = getattr(Batch, "code", None) or getattr(Batch, "batch_code", None)
    if col is None:
        raise AssertionError("Batch 模型缺少批次码列（code/batch_code）")
    return col


def _has_col(model, name: str) -> bool:
    return name in getattr(model.__table__, "c", {})


# -------------------- 台账字段自适配（不写 stock_id） --------------------
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
            else (
                "refline"
                if hasattr(StockLedger, "refline")
                else ("line" if hasattr(StockLedger, "line") else None)
            )
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


# -------------------- 统一的 Ledger SQL 写入（保证 item_id 必写） --------------------
def _to_ref_line_int(ref_line: int | str | None) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib

    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)


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
    """
    直接用 SQL 文本写入台账，确保 item_id 始终写入：
    - 兼容 ORM 未映射新列的场景（例如迁移已加列、模型尚未更新）
    - 统一把 ref_line 映射为稳定整数，保证与 UQ(reason, ref, ref_line) 语义一致
    """
    ts = occurred_at or datetime.now(UTC)
    rline = _to_ref_line_int(ref_line)

    cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at"]
    vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts"]

    if stock_id is not None:
        cols.insert(0, "stock_id")
        vals.insert(0, ":sid")
    if after_qty is not None and hasattr(StockLedger, "after_qty"):
        cols.append("after_qty")
        vals.append(":after")

    sql = f"INSERT INTO stock_ledger ({', '.join(cols)}) VALUES ({', '.join(vals)})"
    params = {
        "sid": stock_id,
        "item": item_id,
        "reason": reason,
        "ref": ref,
        "rline": rline,
        "delta": int(delta),
        "ts": ts,
        "after": int(after_qty or 0),
    }
    await session.execute(text(sql), params)


# ==============================================================================


class StockService:
    def __init__(self, db: Session | None = None):
        self.db = db

    # ==================== 公共入口 ====================
    def adjust(self, **kwargs):
        if "session" in kwargs:
            return self._adjust_async(**kwargs)
        return self.adjust_sync(**kwargs)

    # ==================== Ledger-only 需要的两个 Helper ====================
    async def _ensure_default_warehouse_and_stage(self, session: AsyncSession) -> int:
        # 仓库 1
        wid = (
            await session.execute(select(Warehouse.id).where(Warehouse.id == 1).limit(1))
        ).scalar_one_or_none()
        if wid is None:
            res = await session.execute(
                insert(Warehouse).values({"id": 1, "name": "AUTO-WH"}).returning(Warehouse.id)
            )
            wid = int(res.scalar_one())
        # 库位 0
        loc = (
            await session.execute(select(Location.id).where(Location.id == 0).limit(1))
        ).scalar_one_or_none()
        if loc is None:
            vals = {"id": 0, "warehouse_id": wid}
            if hasattr(Location, "name"):
                vals["name"] = "STAGE"
            await session.execute(insert(Location).values(vals))
        return 0

    async def _get_or_create_zero_stock(
        self, session: AsyncSession, *, item_id: int, location_id: int
    ) -> tuple[int, float]:
        qty_col = _stocks_qty_column()
        row = (
            await session.execute(
                select(Stock.id, qty_col)
                .where(Stock.item_id == item_id, Stock.location_id == location_id)
                .limit(1)
            )
        ).first()
        if row:
            sid, cur = int(row[0]), float(row[1] or 0.0)
            return sid, cur
        res = await session.execute(
            insert(Stock)
            .values({"item_id": item_id, "location_id": location_id, qty_col.key: 0})
            .returning(Stock.id)
        )
        sid = int(res.scalar_one())
        return sid, 0.0

    # ==================== 异步入口（增强版） ====================
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

        # 路径 A：location_id 缺失 → 仅记台账（ledger-only）
        if location_id is None:
            batch_id = None
            if batch_code and production_date and expiry_date:
                batch_id = await self._ensure_batch_minimal(
                    session=session,
                    item_id=item_id,
                    batch_code=batch_code,
                    production_date=production_date,
                    expiry_date=expiry_date,
                )

            await self._ensure_item_exists(session, item_id=item_id)
            stage_loc = await self._ensure_default_warehouse_and_stage(session)
            stock_id, cur_qty = await self._get_or_create_zero_stock(
                session, item_id=item_id, location_id=stage_loc
            )

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
            return {
                "ledger_id": None,
                "batch_id": batch_id,
                "stock_id": stock_id,
                "stocks_touched": False,
                "note": "no location_id; ledger-only bound to STAGE(0)",
            }

        # 路径 B：有 location_id → 正常库存路径
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

        # 正数 → NORMAL 入库
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

    # ==================== NORMAL 入库（带 stock_id；批次按 FULL/Minimal 自适配） ====================
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

        # 批次：信息充分时建立；若 Batch 表带 location/warehouse，则使用 FULL 方案
        batch_id = None
        if batch_code and production_date and expiry_date:
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

        # 先确保 stocks 行，拿到 (stock_id, before)
        stock_id, before = await self._ensure_stock_row(
            session, item_id=item_id, location_id=location_id
        )
        after = before + float(delta)

        # 汇总库存增量
        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=float(delta)
        )

        # 写台账：统一 SQL，确保 item_id 写入
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

    # ==================== 直接按批次出库（定向） ====================
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

        has_qty = _has_col(Batch, "qty")
        code_attr = _batch_code_attr()

        q = select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code)
        r = (await session.execute(q)).scalar_one_or_none()
        if r is None and (batch_code is not None):
            r = await self._ensure_batch_minimal(
                session,
                item_id=item_id,
                batch_code=batch_code,
                production_date=None,
                expiry_date=None,
            )
        batch_id = int(r) if r is not None else None

        if has_qty and batch_id is not None:
            await _exec_with_retry(
                session,
                update(Batch)
                .where(Batch.id == batch_id)
                .values(qty=func.coalesce(Batch.qty, 0) - int(amount)),
            )

        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        after = before - float(amount)
        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=-float(amount)
        )

        # 统一 SQL 写台账
        sid, _ = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)
        await _write_ledger_sql(
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
            "batch_moves": (
                [(batch_id, -float(amount))] if (has_qty and batch_id is not None) else []
            ),
            "stock_after": int(stock_after),
            "stocks_touched": True,
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
        today = date.today()
        code_attr = _batch_code_attr()
        has_qty = _has_col(Batch, "qty")
        has_expiry = _has_col(Batch, "expiry_date")

        conds = [Batch.item_id == item_id]
        if has_qty:
            conds.append(Batch.qty > 0)
        if has_expiry and not allow_expired:
            conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        order_cols: Iterable = (
            [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
            if has_expiry and not allow_expired
            else [Batch.id.asc()]
        )

        rows = (
            await session.execute(
                select(
                    Batch.id,
                    Batch.expiry_date if has_expiry else Batch.id.label("expiry_date"),
                    Batch.qty if has_qty else func.null(),
                )
                .where(and_(*conds))
                .order_by(*order_cols)
            )
        ).all()

        need = -float(delta)
        moves: list[tuple[int, float]] = []
        for r in rows:
            if need <= 0:
                break
            available = float(r.qty or 0.0) if has_qty else need
            if available <= 0:
                continue
            take = min(need, available)
            moves.append((int(r.id), -take))
            need -= take

        if need > 1e-12:
            raise ValueError("库存不足，无法按 FEFO 出库")

        sid, _cur = await self._ensure_stock_row(session, item_id=item_id, location_id=location_id)

        before = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        running = before
        last_ledger_id = None

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
            last_ledger_id = last_ledger_id  # 占位，无需回读 id

        await self._bump_stock(
            session, item_id=item_id, location_id=location_id, delta=float(delta)
        )
        await session.commit()

        stock_after = await self._get_current_qty(session, item_id=item_id, location_id=location_id)
        return {
            "total_delta": float(delta),
            "batch_moves": moves,
            "stock_after": int(stock_after),
            "ledger_id": (int(last_ledger_id) if last_ledger_id is not None else None),
            "stocks_touched": True,
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
        if not _has_col(Batch, "expiry_date") or not _has_col(Batch, "qty"):
            return {"warehouse_id": warehouse_id, "moved_total": 0, "moves": []}

        today = date.today()
        if to_location_id is None:
            to_location_id = await self._ensure_location(session, warehouse_id, to_location_name)

        conds = [
            Batch.warehouse_id == warehouse_id,
            Batch.qty > 0,
            Batch.expiry_date < today,
        ]
        if item_ids:
            conds.append(Batch.item_id.in_(item_ids))

        rows = (
            await session.execute(
                select(
                    Batch.id,
                    Batch.item_id,
                    Batch.location_id,
                    _batch_code_attr().label("code"),
                    Batch.qty,
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

            await self._bump_stock(
                session, item_id=item_id, location_id=src_loc, delta=-qty_to_move
            )
            await self._bump_stock(
                session, item_id=item_id, location_id=to_location_id, delta=+qty_to_move
            )

            # 两条台账：这里也可切换到 _write_ledger_sql，如果需要记录 item_id/occurred_at/after_qty
            session.add(
                _make_ledger(
                    op=reason,
                    item_id=item_id if hasattr(StockLedger, "item_id") else None,
                    location_id=src_loc if hasattr(StockLedger, "location_id") else None,
                    batch_id=int(bid),
                    delta=-qty_to_move,
                    ref=ref,
                )
            )
            session.add(
                _make_ledger(
                    op=reason,
                    item_id=item_id if hasattr(StockLedger, "item_id") else None,
                    location_id=to_location_id if hasattr(StockLedger, "location_id") else None,
                    batch_id=int(dst_bid),
                    delta=qty_to_move,
                    ref=ref,
                )
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

        return {
            "warehouse_id": warehouse_id,
            "moved_total": moved_total,
            "moves": moves,
        }

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

        has_qty = _has_col(Batch, "qty")
        has_expiry = _has_col(Batch, "expiry_date")
        code_attr = _batch_code_attr()
        today = date.today()

        conds = [Batch.item_id == item_id]
        if has_qty:
            conds.append(Batch.qty > 0)
        if has_expiry and not allow_expired:
            conds.append((Batch.expiry_date.is_(None)) | (Batch.expiry_date >= today))

        order_cols: Iterable = (
            [
                case((Batch.expiry_date.is_(None), 1), else_=0),
                Batch.expiry_date.asc().nulls_last(),
                Batch.id.asc(),
            ]
            if has_expiry and not allow_expired
            else [Batch.id.asc()]
        )

        rows = (
            await session.execute(
                select(
                    Batch.id,
                    code_attr.label("code"),
                    Batch.expiry_date if has_expiry else func.null(),
                    Batch.production_date if _has_col(Batch, "production_date") else func.null(),
                    Batch.qty if has_qty else func.null(),
                )
                .where(and_(*conds))
                .order_by(*order_cols)
            )
        ).all()

        if not rows:
            raise ValueError("源库位无可用批次")

        need = float(qty)
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
            available = float(r.qty or 0) if has_qty else need
            if available <= 0:
                continue
            take = min(need, available)
            need -= take

            if has_qty:
                await _exec_with_retry(
                    session,
                    update(Batch)
                    .where(Batch.id == r.id)
                    .values(qty=func.coalesce(Batch.qty, 0) - int(take)),
                )
            src_after -= take
            session.add(
                _make_ledger(
                    op=reason,
                    item_id=item_id,
                    location_id=src_location_id,
                    batch_id=int(r.id),
                    delta=-int(take),
                    ref=ref,
                    after_qty=int(src_after),
                )
            )

            dst_bid = await self._ensure_batch_minimal(
                session=session,
                item_id=item_id,
                batch_code=r.code,
                production_date=(r.production_date if _has_col(Batch, "production_date") else None),
                expiry_date=(r.expiry_date if has_expiry else None),
            )
            if has_qty:
                await _exec_with_retry(
                    session,
                    update(Batch)
                    .where(Batch.id == dst_bid)
                    .values(qty=func.coalesce(Batch.qty, 0) + int(take)),
                )
            dst_after += take
            session.add(
                _make_ledger(
                    op=reason,
                    item_id=item_id,
                    location_id=dst_location_id,
                    batch_id=int(dst_bid),
                    delta=int(take),
                    ref=ref,
                    after_qty=int(dst_after),
                )
            )

            moves.append(
                dict(
                    src_batch_id=int(r.id),
                    dst_batch_id=int(dst_bid),
                    batch_code=r.code,
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
        qty_col = _stocks_qty_column()
        q = select(qty_col).where(Stock.item_id == item_id, Stock.location_id == location_id)
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
                session,
                insert(Warehouse).values({"name": "AUTO-WH"}).returning(Warehouse.id),
            )
            wid_new = int(res_w.scalar_one())
        else:
            wid_new = int(w_first)

        try:
            await _exec_with_retry(
                session,
                insert(Location).values(
                    {
                        "id": location_id,
                        "name": f"AUTO-LOC-{location_id}",
                        "warehouse_id": wid_new,
                    }
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
        vals: dict = {
            "id": item_id,
            "sku": f"ITEM-{item_id}",
            "name": f"Auto Item {item_id}",
        }
        for fld in (
            "qty_available",
            "qty_on_hand",
            "qty_reserved",
            "qty",
            "min_qty",
            "max_qty",
        ):
            if hasattr(Item, fld):
                vals.setdefault(fld, 0)
        if hasattr(Item, "unit"):
            vals.setdefault("unit", "EA")
        try:
            await _exec_with_retry(session, insert(Item).values(vals))
        except IntegrityError:
            await session.rollback()

    async def _ensure_batch_minimal(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        batch_code: str,
        production_date: date | None,
        expiry_date: date | None,
    ) -> int:
        code_attr = _batch_code_attr()
        existed = (
            await session.execute(
                select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code)
            )
        ).scalar_one_or_none()
        if existed:
            return int(existed)

        vals: dict[str, Any] = {"item_id": item_id}
        vals[code_attr.key] = batch_code
        if _has_col(Batch, "production_date"):
            vals["production_date"] = production_date
        if _has_col(Batch, "expiry_date"):
            vals["expiry_date"] = expiry_date
        if _has_col(Batch, "qty"):
            vals["qty"] = 0

        try:
            rid = (
                await _exec_with_retry(session, insert(Batch).values(vals).returning(Batch.id))
            ).scalar_one()
            return int(rid)
        except IntegrityError:
            if _has_col(Batch, "location_id") or _has_col(Batch, "warehouse_id"):
                pass
            await session.rollback()
            rid2 = (
                await session.execute(
                    select(Batch.id).where(Batch.item_id == item_id, code_attr == batch_code)
                )
            ).scalar_one_or_none()
            if rid2 is not None:
                return int(rid2)
            raise

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
        if not (_has_col(Batch, "warehouse_id") and _has_col(Batch, "location_id")):
            return await self._ensure_batch_minimal(
                session=session,
                item_id=item_id,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
            )

        code_attr = _batch_code_attr()
        conds = [
            Batch.item_id == item_id,
            Batch.warehouse_id == warehouse_id,
            Batch.location_id == location_id,
            code_attr == batch_code,
        ]
        existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
        if existed:
            return int(existed)

        vals: dict[str, Any] = {
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "location_id": location_id,
            code_attr.key: batch_code,
        }
        if _has_col(Batch, "qty"):
            vals["qty"] = 0
        if _has_col(Batch, "production_date"):
            vals["production_date"] = production_date
        if _has_col(Batch, "expiry_date"):
            vals["expiry_date"] = expiry_date

        try:
            rid = (
                await _exec_with_retry(session, insert(Batch).values(vals).returning(Batch.id))
            ).scalar_one()
            return int(rid)
        except IntegrityError:
            await session.rollback()
            rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
            return int(rid2)

    async def _bump_stock(
        self, session: AsyncSession, *, item_id: int, location_id: int, delta: float
    ) -> None:
        qty_col = _stocks_qty_column()
        cur = (
            await session.execute(
                select(qty_col).where(Stock.item_id == item_id, Stock.location_id == location_id)
            )
        ).scalar_one_or_none()
        if cur is None:
            vals = {
                "item_id": item_id,
                "location_id": location_id,
                qty_col.key: float(delta),
            }
            await _exec_with_retry(session, insert(Stock).values(vals))
            return
        await _exec_with_retry(
            session,
            update(Stock)
            .where(Stock.item_id == item_id, Stock.location_id == location_id)
            .values({qty_col.key: func.coalesce(qty_col, 0) + float(delta)}),
        )

    async def _ensure_stock_row(
        self, session: AsyncSession, *, item_id: int, location_id: int
    ) -> tuple[int, float]:
        qty_col = _stocks_qty_column()
        sid = (
            await session.execute(
                select(Stock.id).where(Stock.item_id == item_id, Stock.location_id == location_id)
            )
        ).scalar_one_or_none()
        if sid is None:
            vals = {"item_id": item_id, "location_id": location_id, qty_col.key: 0.0}
            sid = (
                await _exec_with_retry(session, insert(Stock).values(vals).returning(Stock.id))
            ).scalar_one()
            cur = 0.0
        else:
            cur = (
                await session.execute(select(qty_col).where(Stock.id == sid))
            ).scalar_one_or_none() or 0.0
        return int(sid), float(cur)

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
            if hasattr(Item, "unit"):
                itm.unit = "EA"
            self.db.add(itm)
            self.db.flush()

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
        from sqlalchemy import inspect as _inspect
        from sqlalchemy import text as _text

        assert self.db is not None, "同步模式需要 self.db Session"

        qty_col_obj = getattr(Stock.__table__.c, "quantity", None) or getattr(
            Stock.__table__.c, "qty", None
        )
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
            wh_col = (
                "warehouse_id"
                if "warehouse_id" in db_cols
                else ("warehouse" if "warehouse" in db_cols else None)
            )

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
