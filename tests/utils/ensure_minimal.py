# tests/utils/ensure_minimal.py
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lot_service import ensure_internal_lot_singleton as ensure_internal_lot_singleton_svc
from app.wms.stock.services.lot_service import ensure_lot_full as ensure_lot_full_svc
from app.wms.stock.services.stock_adjust import adjust_lot_impl

UTC = timezone.utc


def _as_lot_id(v: object) -> int:
    """
    lot_service 的 ensure_* 可能返回 int(lot_id) 或 ORM 对象（带 .id）。
    tests 侧用这个函数统一兼容，避免类型漂移导致的 AttributeError。
    """
    return int(getattr(v, "id", v))


def _stable_required_dates_from_code(code_raw: str, *, days: int) -> tuple[date, date]:
    """
    REQUIRED lot helper：按 lot_code 稳定生成日期，避免不同批次都撞到同一天 production_date。
    """
    code = str(code_raw).strip()
    if not code:
        raise ValueError("lot_code empty")

    digest = hashlib.sha1(code.encode("utf-8")).hexdigest()
    offset_days = int(digest[:8], 16) % 73000  # ~200 years range
    production_date = date(2000, 1, 1) + timedelta(days=offset_days)
    expiry_date = production_date + timedelta(days=int(days))
    return production_date, expiry_date


# ---------- warehouses ----------
async def ensure_warehouse(session: AsyncSession, *, id: int, name: Optional[str] = None) -> None:
    name = name or f"WH-{id}"
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": int(id), "name": str(name)},
    )


# ---------- items ----------
async def ensure_item(
    session: AsyncSession,
    *,
    id: int,
    sku: Optional[str] = None,
    name: Optional[str] = None,
    uom: Optional[str] = None,
    expiry_required: bool = False,
) -> None:
    """
    items 表（Phase M-5 终态）：

    - sku NOT NULL, name NOT NULL
    - items.uom 已物理删除（单位真相源唯一为 item_uoms）
    - lot_source_policy / expiry_policy / derivation_allowed / uom_governance_enabled 均 NOT NULL 且无默认

    使用方式：
    - 默认（无有效期）：expiry_required=False -> 不得把已有 REQUIRED 商品刷回 NONE
    - 需要有效期：expiry_required=True  -> 若商品已存在，也要单向提升到 REQUIRED

    参数 uom：历史兼容参数（已不再写入 DB），保留以避免旧测试调用报错。
    """
    sku = sku or f"SKU-{id}"
    name = name or f"ITEM-{id}"
    _ = uom  # deprecated (items.uom removed)

    expiry_policy = "REQUIRED" if expiry_required else "NONE"
    lot_source_policy = "SUPPLIER_ONLY" if expiry_required else "INTERNAL_ONLY"

    await session.execute(
        text(
            """
            INSERT INTO items (
              id, sku, name,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled
            )
            VALUES (
              :id, :sku, :name,
              CAST(:lot_source_policy AS lot_source_policy),
              CAST(:expiry_policy AS expiry_policy),
              TRUE,
              TRUE
            )
            ON CONFLICT (id) DO UPDATE
               SET sku = EXCLUDED.sku,
                   name = EXCLUDED.name,
                   lot_source_policy = CASE
                     WHEN EXCLUDED.expiry_policy = 'REQUIRED'::expiry_policy
                       THEN 'SUPPLIER_ONLY'::lot_source_policy
                     ELSE items.lot_source_policy
                   END,
                   expiry_policy = CASE
                     WHEN EXCLUDED.expiry_policy = 'REQUIRED'::expiry_policy
                       THEN 'REQUIRED'::expiry_policy
                     ELSE items.expiry_policy
                   END,
                   derivation_allowed = CASE
                     WHEN EXCLUDED.expiry_policy = 'REQUIRED'::expiry_policy
                       THEN TRUE
                     ELSE items.derivation_allowed
                   END,
                   uom_governance_enabled = CASE
                     WHEN EXCLUDED.expiry_policy = 'REQUIRED'::expiry_policy
                       THEN TRUE
                     ELSE items.uom_governance_enabled
                   END
            """
        ),
        {
            "id": int(id),
            "sku": str(sku),
            "name": str(name),
            "lot_source_policy": str(lot_source_policy),
            "expiry_policy": str(expiry_policy),
        },
    )


def _norm_lot_key(code_raw: str) -> str:
    # tests baseline normalize: trim + lower (DB unique key is text; service uses upper, but tests just need stable key)
    return str(code_raw).strip().lower()


async def _load_item_expiry_policy(session: AsyncSession, *, item_id: int) -> str:
    r = await session.execute(text("SELECT expiry_policy::text FROM items WHERE id=:i"), {"i": int(item_id)})
    v = r.scalar_one_or_none()
    if v is None:
        raise ValueError(f"item_not_found: {item_id}")
    return str(v)


# ---------- lots / stocks_lot ----------
async def ensure_supplier_lot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
) -> int:
    """
    Phase M-5：创建/获取一个最小合法 SUPPLIER lot，并返回 lot_id。

    ✅ 工程收口：禁止 tests 里直接 INSERT INTO lots
    -> 统一走 app.wms.stock.services.lot_service.ensure_lot_full

    语义收口：
    - helper 名字就叫 ensure_supplier_lot，因此它必须保证商品策略至少提升到 REQUIRED
    - REQUIRED lot 身份已切到 (warehouse_id, item_id, production_date)，
      因此这里必须显式给 production_date
    """
    code_raw = str(lot_code).strip()
    if not code_raw:
        raise ValueError("lot_code empty")

    await ensure_item(
        session,
        id=int(item_id),
        sku=f"SKU-{item_id}",
        name=f"ITEM-{item_id}",
        expiry_required=True,
    )

    expiry_policy = await _load_item_expiry_policy(session, item_id=int(item_id))
    if expiry_policy != "REQUIRED":
        raise RuntimeError(
            f"ensure_supplier_lot expected REQUIRED expiry_policy, got: {expiry_policy}"
        )

    production_date, expiry_date = _stable_required_dates_from_code(code_raw, days=365)

    got = await ensure_lot_full_svc(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_code=code_raw,
        production_date=production_date,
        expiry_date=expiry_date,
    )
    return _as_lot_id(got)


async def ensure_internal_lot_singleton(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
) -> int:
    got = await ensure_internal_lot_singleton_svc(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
    )
    return _as_lot_id(got)


async def _get_stock_qty(session: AsyncSession, *, item_id: int, warehouse_id: int, lot_id: int) -> int:
    r = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks_lot
             WHERE item_id = :i
               AND warehouse_id = :w
               AND lot_id = :lot
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
    )
    v = r.scalar_one_or_none()
    return int(v) if v is not None else 0


async def ensure_stock_slot(session: AsyncSession, *, item_id: int, warehouse_id: int, lot_code: str | None) -> None:
    """
    Phase 4D+：创建 stocks_lot 槽位（测试工具）。

    ✅ 工程收口：禁止 tests 里直接 INSERT INTO stocks_lot
    -> 统一走 adjust_lot_impl（writer 自己 ensure 槽位）
    """
    await set_stock_qty(session, item_id=int(item_id), warehouse_id=int(warehouse_id), lot_code=lot_code, qty=0)


async def set_stock_qty(session: AsyncSession, *, item_id: int, warehouse_id: int, lot_code: str | None, qty: int) -> None:
    """
    Phase 4D+：把 stocks_lot 槽位的 qty 设置为特定值（幂等重置，用于测试）。

    ✅ 工程收口：禁止 tests 里 UPDATE stocks_lot / INSERT stocks_lot
    -> 做法：读当前 qty -> 计算 delta -> 走 adjust_lot_impl 写入（ledger + balance 一致）
    """
    if lot_code is None:
        bc_norm: Optional[str] = None
        lot_id = await ensure_internal_lot_singleton(session, item_id=int(item_id), warehouse_id=int(warehouse_id))
    else:
        bc_norm = (str(lot_code).strip() or None)
        if bc_norm is None:
            lot_id = await ensure_internal_lot_singleton(session, item_id=int(item_id), warehouse_id=int(warehouse_id))
        else:
            lot_id = await ensure_supplier_lot(
                session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_code=bc_norm,
            )

    cur = await _get_stock_qty(session, item_id=int(item_id), warehouse_id=int(warehouse_id), lot_id=int(lot_id))
    target = int(qty)
    delta = target - int(cur)
    if delta == 0:
        return

    expiry_policy = await _load_item_expiry_policy(session, item_id=int(item_id))
    if expiry_policy == "REQUIRED" and int(delta) > 0:
        if bc_norm is None:
            raise RuntimeError(
                f"set_stock_qty requires lot_code for REQUIRED item: item_id={int(item_id)}"
            )
        production_date, expiry_date = _stable_required_dates_from_code(bc_norm, days=365)
    else:
        expiry_date = None
        production_date = None

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=int(delta),
        reason="UT_SET_STOCK_QTY",
        ref="ut:set_stock_qty",
        ref_line=1,
        occurred_at=None,
        meta=None,
        batch_code=bc_norm,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )


# ---------- lot-code-named test helpers ----------
async def ensure_supplier_lot_with_stock(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
    qty: int,
) -> None:
    """
    Test helper: create a SUPPLIER lot by display lot_code and set its stocks_lot qty.

    lot_code is display/input text only; stock identity remains lot_id.
    """
    code_raw = str(lot_code).strip()
    if not code_raw:
        raise ValueError("lot_code empty")

    await ensure_item(session, id=int(item_id))
    await ensure_warehouse(session, id=int(warehouse_id))
    _ = await ensure_supplier_lot(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=code_raw,
    )
    await ensure_stock_slot(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=code_raw,
    )
    await set_stock_qty(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=code_raw,
        qty=int(qty),
    )
