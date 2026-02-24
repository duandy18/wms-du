# app/services/stock_helpers_impl.py
from __future__ import annotations

from sqlalchemy import and_, func, insert, literal, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.models.item import Item
from app.models.stock import Stock
from app.models.warehouse import Warehouse

# ======================== 通用执行（带退避） ========================


async def exec_retry(session: AsyncSession, stmt, params=None):
    """
    统一执行器：对短暂锁冲突做指数退避，不改变隔离级别。
    """
    import asyncio
    import random

    base, mx = 0.03, 0.35
    for i in range(24):
        try:
            return await (session.execute(stmt) if params is None else session.execute(stmt, params))
        except OperationalError as e:
            msg = (str(e) or "").lower()
            if ("database is locked" not in msg and "database is busy" not in msg) or i >= 23:
                raise
            backoff = min(mx, base * (1.8 ** (i + 1)))
            await asyncio.sleep(backoff * (0.6 + 0.4 * random.random()))


# ======================== 列访问器（固定契约） ========================


def stock_qty_col():
    col = getattr(Stock, "qty", None)
    if col is None:
        raise AssertionError("stocks 缺少 qty 列")
    return col


def batch_qty_col():
    """
    兼容：若 Batch 没有 qty 列，则返回常量 0（仅用于查询/表达式场景）。
    注意：INSERT/UPDATE 时请先判断 hasattr(Batch, 'qty') 再写入。
    """
    col = getattr(Batch, "qty", None)
    if col is None:
        return literal(0).label("qty")
    return col


def batch_code_attr():
    col = getattr(Batch, "batch_code", None)
    if col is None:
        raise AssertionError("batches 缺少 batch_code 列")
    return col


# ======================== 基础兜底（不含 location） ========================


async def ensure_item(session: AsyncSession, item_id: int) -> None:
    exists = (await session.execute(select(Item.id).where(Item.id == item_id))).scalar_one_or_none()
    if exists is not None:
        return
    try:
        await exec_retry(
            session,
            insert(Item).values({"id": item_id, "sku": f"ITEM-{item_id}", "name": f"Auto Item {item_id}"}),
        )
    except IntegrityError:
        await session.rollback()


async def ensure_warehouse(session: AsyncSession, warehouse_id: int) -> None:
    exists = (await session.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id))).scalar_one_or_none()
    if exists is not None:
        return
    try:
        await exec_retry(session, insert(Warehouse).values({"id": int(warehouse_id), "name": f"AUTO-WH-{warehouse_id}"}))
    except IntegrityError:
        await session.rollback()


# ======================== 维度工具（batch_code 归一） ========================


def _norm_batch_code(batch_code: str | None) -> str | None:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


# ======================== stocks 槽位（item + wh + batch_code_key） ========================


async def ensure_stock_slot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None,
) -> None:
    """
    在 stocks 维度的“空槽位”（qty=0）。

    ✅ DB 唯一性：uq_stocks_item_wh_batch = (item_id, warehouse_id, batch_code_key)
    - batch_code 允许 None（无批次槽位）
    """
    bc_norm = _norm_batch_code(batch_code)
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:i, :w, :c, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": bc_norm},
    )


async def ensure_stock_row(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None = None,
) -> tuple[int, float]:
    """
    返回：stock_id, before_qty（按当前唯一维度：item_id + warehouse_id + batch_code_key）
    """
    bc_norm = _norm_batch_code(batch_code)

    await ensure_stock_slot(session, item_id=int(item_id), warehouse_id=int(warehouse_id), batch_code=bc_norm)

    row = await session.execute(
        text(
            """
            SELECT id, qty
              FROM stocks
             WHERE item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": bc_norm},
    )
    rec = row.first()
    if not rec:
        raise RuntimeError("ensure_stock_row failed to materialize stock row")
    return int(rec[0]), float(rec[1] or 0.0)


# ======================== 精确加减（按 stock_id） ========================


async def bump_stock_by_stock_id(session: AsyncSession, *, stock_id: int, delta: float) -> None:
    """按 stocks.id 精确加减。"""
    qcol = stock_qty_col()
    await exec_retry(
        session,
        update(Stock).where(Stock.id == stock_id).values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


# ======================== 兼容：按 item+warehouse 的粗粒度加减 ========================


async def bump_stock(session: AsyncSession, *, item_id: int, warehouse_id: int, delta: float) -> None:
    """
    无 location 版本：对该 warehouse 下该 item 的所有批次行做汇总更新。
    若该 item 在该 warehouse 下没有任何 stocks 行，则创建一个 “无批次(NULL) 槽位” 承接 delta。
    """
    qcol = stock_qty_col()

    any_sid = (
        await session.execute(select(Stock.id).where(Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id)).limit(1))
    ).scalar_one_or_none()

    if any_sid is None:
        await exec_retry(
            session,
            insert(Stock).values(
                {
                    "item_id": int(item_id),
                    "warehouse_id": int(warehouse_id),
                    "batch_code": None,
                    qcol.key: float(delta),
                }
            ),
        )
        return

    await exec_retry(
        session,
        update(Stock)
        .where(Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id))
        .values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


# ======================== 查询 ========================


async def get_current_qty(session: AsyncSession, *, item_id: int, warehouse_id: int) -> float:
    """
    无 location 版本：汇总该 warehouse 下该 item 的 qty。
    """
    qcol = stock_qty_col()
    val = (
        await session.execute(
            select(func.coalesce(func.sum(qcol), 0)).where(Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id))
        )
    ).scalar_one()
    return float(val or 0.0)


# ======================== 批次行兜底 / UPSERT（供 inbound 等调用） ========================


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    确保 batches 行存在并补齐必要字段；返回 batch_id（幂等）。
    若模型无 Batch.qty，则不写入该字段（数量只在 stocks 维护）。

    ✅ batches 当前唯一约束：uq_batches_item_wh_code / uq_batches_wh_item_code
    (item_id, warehouse_id, batch_code) / (warehouse_id, item_id, batch_code)
    """
    code_attr = batch_code_attr()

    conds = [
        Batch.item_id == item_id,
        Batch.warehouse_id == warehouse_id,
        code_attr == batch_code,
    ]
    existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
    if existed:
        return int(existed)

    vals = {
        "item_id": item_id,
        "warehouse_id": warehouse_id,
        code_attr.key: batch_code,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
    if hasattr(Batch, "qty"):
        vals["qty"] = 0

    try:
        rid = (await exec_retry(session, insert(Batch).values(vals).returning(Batch.id))).scalar_one()
        return int(rid)
    except IntegrityError:
        await session.rollback()
        rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
        return int(rid2)
