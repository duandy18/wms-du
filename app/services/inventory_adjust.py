# app/services/inventory_adjust.py
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import List, Tuple

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.services.ledger_writer import write_ledger
from app.services.stock_helpers import (
    batch_code_attr,
    batch_qty_col,
    bump_stock_by_stock_id,
    ensure_batch_full,
    ensure_stock_row,
    exec_retry,
    resolve_warehouse_by_location,
)


class InventoryAdjust:
    """入库（NORMAL）与 FEFO 出库。仅执行 SQL，flush/commit 交由上层控制。"""

    @staticmethod
    async def inbound(
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
            raise ValueError("inbound 仅支持正数 delta")

        bq = batch_qty_col()
        batch_id = None
        batch_after = None

        # 1) 批次存在性
        if batch_code:
            wh_id = await resolve_warehouse_by_location(session, location_id)
            batch_id = await ensure_batch_full(
                session=session,
                item_id=item_id,
                warehouse_id=wh_id,
                location_id=location_id,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
            )

        # 2) stocks 行
        stock_id, _ = await ensure_stock_row(
            session,
            item_id=item_id,
            location_id=location_id,
            batch_code=batch_code,
        )

        # 3) 清理 SQLAlchemy 缓存，防止重复加（先 flush，再同步 expire_all）
        await session.flush()
        session.expire_all()

        # 4) 查询当前库存（实时）
        row = await session.execute(
            text("SELECT qty FROM stocks WHERE id=:sid"),
            {"sid": stock_id},
        )
        current_qty = float(row.scalar() or 0.0)
        after_qty = current_qty + float(delta)

        # 5) 更新批次表
        if batch_id is not None:
            await exec_retry(
                session,
                update(Batch)
                .where(Batch.id == batch_id)
                .values({bq.key: func.coalesce(bq, 0) + int(delta)}),
            )

        # 6) 更新 stocks
        await bump_stock_by_stock_id(session, stock_id=stock_id, delta=float(delta))

        # 7) 写 ledger
        ledger_id = await write_ledger(
            session,
            stock_id=stock_id,
            item_id=item_id,
            reason=reason or "INBOUND",
            delta=int(delta),
            after_qty=int(after_qty),
            ref=ref,
            ref_line=1,
            occurred_at=datetime.now(UTC),
        )

        # 不再 flush / commit，让上层统一处理
        return {
            "total_delta": float(delta),
            "batch_moves": ([(batch_id, float(delta))] if batch_id is not None else []),
            "stock_after": int(after_qty),
            "batch_after": batch_after,
            "ledger_id": int(ledger_id),
            "stocks_touched": True,
        }

    @staticmethod
    async def fefo_outbound(
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        delta: float,  # 负数
        reason: str,
        ref: str | None,
        allow_expired: bool,
        batch_code: str | None = None,
    ) -> dict:
        if delta >= 0:
            raise ValueError("fefo_outbound 仅支持负数 delta")

        today = date.today()
        bq = batch_qty_col()
        code_attr = batch_code_attr()

        def _sel(where_clause):
            return (
                select(Batch.id, code_attr.label("code"), Batch.expiry_date, bq.label("qty"))
                .where(
                    and_(
                        Batch.item_id == item_id,
                        Batch.location_id == location_id,
                        func.coalesce(bq, 0) > 0,
                        where_clause,
                    )
                )
                .order_by(Batch.expiry_date.asc().nulls_last(), Batch.id.asc())
            )

        expired = (await session.execute(_sel(Batch.expiry_date < today))).all()
        valid = (await session.execute(_sel(Batch.expiry_date >= today))).all()
        nulls = (await session.execute(_sel(Batch.expiry_date.is_(None)))).all()

        seq: List[Tuple[int, str, float]] = []
        if (reason or "").upper() == "CYCLE_COUNT_DOWN":
            seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in expired]
            seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in valid]
            seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in nulls]
        else:
            if allow_expired:
                seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in expired]
            seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in valid]
            seq += [(int(r.id), r.code, float(r.qty or 0.0)) for r in nulls]

        need = -float(delta)
        moves: list[tuple[int, str, float]] = []
        for bid, code, avail in seq:
            if need <= 0:
                break
            take = min(need, float(avail or 0.0))
            if take <= 0:
                continue
            moves.append((bid, code, -take))
            need -= take
        if need > 1e-12:
            raise ValueError("库存不足，无法按 FEFO 出库")

        last_ledger_id = None
        total_used = 0.0

        for bid, code, used in moves:
            sid, before = await ensure_stock_row(
                session,
                item_id=item_id,
                location_id=location_id,
                batch_code=code,
            )
            after = before + float(used)

            lid = await write_ledger(
                session,
                stock_id=sid,
                item_id=item_id,
                reason=reason or "FEFO",
                delta=int(used),
                after_qty=int(after),
                ref=ref,
                ref_line=1,
                occurred_at=datetime.now(UTC),
            )
            last_ledger_id = int(lid)

            await exec_retry(
                session,
                update(Batch)
                .where(Batch.id == bid)
                .values({bq.key: func.coalesce(bq, 0) + int(used)}),
            )
            await bump_stock_by_stock_id(session, stock_id=sid, delta=float(used))
            total_used += -float(used)

        # 不再 flush / commit
        return {
            "total_delta": -total_used,
            "batch_moves": [(bid, used) for (bid, _code, used) in moves],
            "stock_after": None,
            "batch_after": None,
            "ledger_id": last_ledger_id,
            "stocks_touched": True,
        }
