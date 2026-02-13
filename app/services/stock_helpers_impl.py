# app/services/stock_helpers_impl.py
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
            return await (session.execute(stmt) if params is None else session.execute(stmt, params))
        except OperationalError as e:
            msg = (str(e) or "").lower()
            if ("database is locked" not in msg and "database is busy" not in msg) or i >= 23:
                raise
            backoff = min(mx, base * (1.8 ** (i + 1)))
            await asyncio.sleep(backoff * (0.6 + 0.4 * random.random()))


# ======================== scope 工具 ========================


def _norm_scope(scope: str | None) -> str:
    sc = (scope or "PROD").strip().upper()
    if sc not in {"PROD", "DRILL"}:
        raise ValueError("scope must be PROD|DRILL")
    return sc


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
            insert(Item).values({"id": item_id, "sku": f"ITEM-{item_id}", "name": f"Auto Item {item_id}"}),
        )
    except IntegrityError:
        await session.rollback()


async def resolve_warehouse_by_location(session: AsyncSession, location_id: int) -> int:
    wid = (await session.execute(select(Location.warehouse_id).where(Location.id == location_id))).scalar_one_or_none()
    if wid is not None:
        return int(wid)

    # 自动兜底：没有就创建默认仓与库位
    w_first = (await session.execute(select(Warehouse.id).order_by(Warehouse.id.asc()))).scalar_one_or_none()
    if w_first is None:
        wid = int((await exec_retry(session, insert(Warehouse).values({"name": "AUTO-WH"}).returning(Warehouse.id))).scalar_one())
    else:
        wid = int(w_first)

    try:
        await exec_retry(
            session,
            insert(Location).values({"id": location_id, "name": f"AUTO-LOC-{location_id}", "warehouse_id": wid}),
        )
    except IntegrityError:
        pass

    return wid


# ======================== stocks 槽位（新宇宙观：scope + item + wh + batch_code_key） ========================


async def ensure_stock_slot(
    session: AsyncSession,
    *,
    scope: str | None = "PROD",
    item_id: int,
    warehouse_id: int,
    location_id: int,
    batch_code: str | None,
) -> None:
    """
    在 stocks 维度的“空槽位”（qty=0）。

    ✅ 重要：当前 DB 唯一性为 uq_stocks_item_wh_batch = (scope, item_id, warehouse_id, batch_code_key)，
    location_id 不再是唯一维度，因此这里必须使用 ON CONFLICT ON CONSTRAINT。

    说明：
    - location_id 参数保留仅为兼容调用方；stocks 的唯一性不依赖它。
    - batch_code 允许 None（无批次槽位）。
    """
    sc = _norm_scope(scope)
    await session.execute(
        text(
            """
            INSERT INTO stocks (scope, item_id, warehouse_id, location_id, batch_code, qty)
            VALUES (:sc, :i, :w, :l, :c, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"sc": sc, "i": int(item_id), "w": int(warehouse_id), "l": int(location_id), "c": batch_code},
    )


# ======================== stocks 行维护（兼容旧接口，但按新唯一维度落地） ========================


async def ensure_stock_row(
    session: AsyncSession,
    *,
    scope: str | None = "PROD",
    item_id: int,
    location_id: int,
    batch_code: str | None = None,
) -> tuple[int, float]:
    """
    返回：stock_id, before_qty（按当前唯一维度：scope + item_id + warehouse_id + batch_code_key）

    兼容旧调用：
    - 仍接收 location_id，但内部先 resolve warehouse_id
    - 不再用 location_id 参与 stocks 行定位（因为 DB 不再保证该维度唯一）
    """
    sc = _norm_scope(scope)

    wid = (await session.execute(select(Location.warehouse_id).where(Location.id == location_id))).scalar_one_or_none()
    if wid is None:
        raise ValueError(f"locations({location_id}) missing; cannot resolve warehouse_id")

    bc_norm: str | None
    if batch_code is None:
        bc_norm = None
    else:
        s = str(batch_code).strip()
        bc_norm = s or None

    await ensure_stock_slot(
        session,
        scope=sc,
        item_id=int(item_id),
        warehouse_id=int(wid),
        location_id=int(location_id),
        batch_code=bc_norm,
    )

    row = await session.execute(
        text(
            """
            SELECT id, qty
              FROM stocks
             WHERE scope = :sc
               AND item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
             LIMIT 1
            """
        ),
        {"sc": sc, "i": int(item_id), "w": int(wid), "c": bc_norm},
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


# ======================== 兼容：按 item+loc 的粗粒度加减 ========================


async def bump_stock(session: AsyncSession, *, scope: str | None = "PROD", item_id: int, location_id: int, delta: float) -> None:
    """
    保留旧接口（部分路径可能还在用）。

    旧语义：按 loc 汇总全部批次行。
    新现实：stocks 的唯一性不再以 location_id 区分，因此这里按 location -> warehouse 归一后，
            对该 warehouse 下该 item 的所有批次行做汇总更新。

    如果该 item 在该 warehouse 下没有任何 stocks 行，则创建一个 “无批次(NULL) 槽位” 来承接 delta。
    """
    sc = _norm_scope(scope)

    wid = await resolve_warehouse_by_location(session, location_id)
    qcol = stock_qty_col()

    # 是否已有任意 stocks 行
    any_sid = (
        await session.execute(
            select(Stock.id)
            .where(
                Stock.scope == sc,
                Stock.item_id == int(item_id),
                Stock.warehouse_id == int(wid),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if any_sid is None:
        # 落到无批次槽位（batch_code=NULL）
        await exec_retry(
            session,
            insert(Stock).values(
                {
                    "scope": sc,
                    "item_id": int(item_id),
                    "warehouse_id": int(wid),
                    "location_id": int(location_id),
                    "batch_code": None,
                    qcol.key: float(delta),
                }
            ),
        )
        return

    # 已有行：对该 warehouse 下该 item 的所有行一起加减（按 scope 隔离）
    await exec_retry(
        session,
        update(Stock)
        .where(
            Stock.scope == sc,
            Stock.item_id == int(item_id),
            Stock.warehouse_id == int(wid),
        )
        .values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


# ======================== 查询 ========================


async def get_current_qty(session: AsyncSession, *, scope: str | None = "PROD", item_id: int, location_id: int) -> float:
    """
    旧语义：汇总该 loc 下所有批次的 qty。
    新现实：location_id 不再是 stocks 唯一维度，因此按 location -> warehouse 归一后汇总。
    """
    sc = _norm_scope(scope)

    wid = await resolve_warehouse_by_location(session, location_id)
    qcol = stock_qty_col()
    val = (
        await session.execute(
            select(func.coalesce(func.sum(qcol), 0)).where(
                Stock.scope == sc,
                Stock.item_id == int(item_id),
                Stock.warehouse_id == int(wid),
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
    if hasattr(Batch, "qty"):
        vals["qty"] = 0

    try:
        rid = (await exec_retry(session, insert(Batch).values(vals).returning(Batch.id))).scalar_one()
        return int(rid)
    except IntegrityError:
        await session.rollback()
        rid2 = (await session.execute(select(Batch.id).where(and_(*conds)))).scalar_one()
        return int(rid2)
