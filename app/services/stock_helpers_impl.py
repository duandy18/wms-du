# app/services/stock_helpers_impl.py
from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
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


def _phase4e_legacy_disabled(name: str) -> None:
    raise RuntimeError(
        f"Phase 4E: legacy helper '{name}' 已禁用。"
        "禁止读取/写入 legacy stocks / legacy batch 表；请改用 lot-world（stocks_lot + lots）与对应服务实现。"
    )


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


# ======================== legacy: stocks 槽位 / mutate / query（Phase 4E 禁用） ========================


def stock_qty_col():
    _phase4e_legacy_disabled("stock_qty_col")


def batch_qty_col():
    _phase4e_legacy_disabled("batch_qty_col")


def batch_code_attr():
    _phase4e_legacy_disabled("batch_code_attr")


async def ensure_stock_slot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None,
) -> None:
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = batch_code
    _phase4e_legacy_disabled("ensure_stock_slot")


async def ensure_stock_row(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None = None,
) -> tuple[int, float]:
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = batch_code
    _phase4e_legacy_disabled("ensure_stock_row")
    return (0, 0.0)


async def bump_stock_by_stock_id(session: AsyncSession, *, stock_id: int, delta: float) -> None:
    _ = session
    _ = stock_id
    _ = delta
    _phase4e_legacy_disabled("bump_stock_by_stock_id")


async def bump_stock(session: AsyncSession, *, item_id: int, warehouse_id: int, delta: float) -> None:
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = delta
    _phase4e_legacy_disabled("bump_stock")


async def get_current_qty(session: AsyncSession, *, item_id: int, warehouse_id: int) -> float:
    _ = session
    _ = item_id
    _ = warehouse_id
    _phase4e_legacy_disabled("get_current_qty")
    return 0.0


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
    legacy batch 表：Phase 4E 禁用。

    Phase 4E：
    - 批次实体应由 lots 承载（lot_code / production_date / expiry_date）
    - 数量应由 stocks_lot 承载（qty）
    """
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = batch_code
    _ = production_date
    _ = expiry_date
    _phase4e_legacy_disabled("ensure_batch_full")
    return 0
