# app/services/stock_helpers.py
from __future__ import annotations

from sqlalchemy import and_, func, insert, literal, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.models.item import Item
from app.models.location import Location
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
            return await (
                session.execute(stmt) if params is None else session.execute(stmt, params)
            )
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


# ======================== 维度/外键兜底 ========================


async def ensure_item(session: AsyncSession, item_id: int) -> None:
    exists = (await session.execute(select(Item.id).where(Item.id == item_id))).scalar_one_or_none()
    if exists is not None:
        return
    try:
        await exec_retry(
            session,
            insert(Item).values(
                {"id": item_id, "sku": f"ITEM-{item_id}", "name": f"Auto Item {item_id}"}
            ),
        )
    except IntegrityError:
        await session.rollback()


async def resolve_warehouse_by_location(session: AsyncSession, location_id: int) -> int:
    wid = (
        await session.execute(select(Location.warehouse_id).where(Location.id == location_id))
    ).scalar_one_or_none()
    if wid is not None:
        return int(wid)

    # 自动兜底：没有就创建默认仓与库位
    w_first = (
        await session.execute(select(Warehouse.id).order_by(Warehouse.id.asc()))
    ).scalar_one_or_none()
    if w_first is None:
        wid = int(
            (
                await exec_retry(
                    session, insert(Warehouse).values({"name": "AUTO-WH"}).returning(Warehouse.id)
                )
            ).scalar_one()
        )
    else:
        wid = int(w_first)

    try:
        await exec_retry(
            session,
            insert(Location).values(
                {"id": location_id, "name": f"AUTO-LOC-{location_id}", "warehouse_id": wid}
            ),
        )
    except IntegrityError:
        pass

    return wid


# ======================== Lock-A：stocks 槽位（新增） ========================


async def ensure_stock_slot(
    session: AsyncSession, *, item_id: int, warehouse_id: int, location_id: int, batch_code: str
) -> None:
    """
    在 stocks 落位 Lock-A 维度的“空槽位”（qty=0）。幂等：冲突即忽略。
    """
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
            VALUES (:i, :w, :l, :c, 0)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO NOTHING
        """
        ),
        {"i": item_id, "w": warehouse_id, "l": location_id, "c": batch_code},
    )


# ======================== stocks 行维护（Lock-A） ========================


async def ensure_stock_row(
    session: AsyncSession, *, item_id: int, location_id: int, batch_code: str | None = None
) -> tuple[int, float]:
    """
    返回：stock_id, before_qty（Lock-A 维度唯一行）
    """
    wid = (
        await session.execute(select(Location.warehouse_id).where(Location.id == location_id))
    ).scalar_one_or_none()
    if wid is None:
        raise ValueError(f"locations({location_id}) missing; cannot resolve warehouse_id")
    if not batch_code:
        raise ValueError("batch_code is required under Lock-A")

    await ensure_stock_slot(
        session,
        item_id=item_id,
        warehouse_id=int(wid),
        location_id=location_id,
        batch_code=batch_code,
    )

    row = await session.execute(
        text(
            """
            SELECT id, qty
              FROM stocks
             WHERE item_id=:i AND warehouse_id=:w AND location_id=:l AND batch_code=:c
             LIMIT 1
        """
        ),
        {"i": item_id, "w": int(wid), "l": location_id, "c": batch_code},
    )
    rec = row.first()
    if not rec:
        raise RuntimeError("ensure_stock_row failed to materialize stock row")
    return int(rec[0]), float(rec[1] or 0.0)


# ======================== 精确加减（按 stock_id） ========================


async def bump_stock_by_stock_id(session: AsyncSession, *, stock_id: int, delta: float) -> None:
    """按 stocks.id 精确加减，适配 Lock-A 维度。"""
    qcol = stock_qty_col()
    await exec_retry(
        session,
        update(Stock)
        .where(Stock.id == stock_id)
        .values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


# ======================== 兼容：按 item+loc 的粗粒度加减 ========================


async def bump_stock(
    session: AsyncSession, *, item_id: int, location_id: int, delta: float
) -> None:
    """
    保留旧接口（部分路径可能还在用）。建议逐步替换为 bump_stock_by_stock_id。
    汇总到该 loc 下的全部批次行。
    """
    qcol = stock_qty_col()
    sid = (
        await session.execute(
            select(Stock.id).where(Stock.item_id == item_id, Stock.location_id == location_id)
        )
    ).scalar_one_or_none()
    if sid is None:
        await exec_retry(
            session,
            insert(Stock).values(
                {"item_id": item_id, "location_id": location_id, qcol.key: float(delta)}
            ),
        )
        return
    await exec_retry(
        session,
        update(Stock)
        .where(Stock.id == sid)
        .values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


# ======================== 查询 ========================


async def get_current_qty(session: AsyncSession, *, item_id: int, location_id: int) -> float:
    """
    汇总该 loc 下所有批次的 qty。
    """
    qcol = stock_qty_col()
    val = (
        await session.execute(
            select(func.coalesce(func.sum(qcol), 0)).where(
                Stock.item_id == item_id, Stock.location_id == location_id
            )
        )
    ).scalar_one()
    return float(val or 0.0)


# ======================== 批次行兜底 / UPSERT（供 inbound 等调用） ========================


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    location_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    确保 batches 行存在并补齐必要字段；返回 batch_id（幂等）。
    若模型无 Batch.qty，则不写入该字段（数量只在 stocks 维护）。
    """
    code_attr = batch_code_attr()

    conds = [
        Batch.item_id == item_id,
        Batch.warehouse_id == warehouse_id,
        Batch.location_id == location_id,
        code_attr == batch_code,
    ]
    existed = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one_or_none()
    if existed:
        return int(existed)

    vals = {
        "item_id": item_id,
        "warehouse_id": warehouse_id,
        "location_id": location_id,
        code_attr.key: batch_code,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
    # 仅在模型存在 qty 列时才写入，避免对不存在列的 insert 报错
    if hasattr(Batch, "qty"):
        vals["qty"] = 0

    try:
        rid = (
            await exec_retry(session, insert(Batch).values(vals).returning(Batch.id))
        ).scalar_one()
        return int(rid)
    except IntegrityError:
        await session.rollback()
        rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
        return int(rid2)
