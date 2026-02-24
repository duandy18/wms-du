# app/services/stock_service_adjust.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.ledger_writer import write_ledger
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item


EnsureBatchFn = Callable[
    ...,
    Awaitable[None],
]


# ----------------------------
# meta helpers
# ----------------------------
def _meta_bool(meta: Optional[Dict[str, Any]], key: str) -> bool:
    if not meta:
        return False
    return meta.get(key) is True


def _meta_str(meta: Optional[Dict[str, Any]], key: str) -> Optional[str]:
    if not meta:
        return None
    v = meta.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError(f"meta.{key} 必须为字符串")
    s = v.strip()
    return s or None


# ----------------------------
# batch helpers (current worldview: batch_code_key)
# ----------------------------
def _norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


def _batch_key(batch_code: Optional[str]) -> str:
    bc = _norm_batch_code(batch_code)
    return bc if bc is not None else "__NULL_BATCH__"


# ----------------------------
# db helpers
# ----------------------------
async def _item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT has_shelf_life
                  FROM items
                 WHERE id = :item_id
                 LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
    ).first()
    if not row:
        return False
    try:
        return bool(row[0] is True)
    except Exception:
        return False


async def _idem_hit_by_batch_key(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code_norm: Optional[str],
    reason: str,
    ref: str,
    ref_line: int,
) -> bool:
    """
    幂等检查（仍基于 batch_code_key）
    """
    idem = await session.execute(
        text(
            """
            SELECT 1
              FROM stock_ledger
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND batch_code_key = :ck
               AND reason       = :r
               AND ref          = :ref
               AND ref_line     = :rl
             LIMIT 1
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "ck": _batch_key(batch_code_norm),
            "r": str(reason),
            "ref": str(ref),
            "rl": int(ref_line),
        },
    )
    return idem.scalar_one_or_none() is not None


async def _ensure_stock_slot_exists(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code_norm: Optional[str],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:i, :w, :c, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": batch_code_norm},
    )


async def _lock_stock_slot_for_update(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code_norm: Optional[str],
) -> tuple[int, int]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id AS sid, qty AS q
                      FROM stocks
                     WHERE item_id=:i
                       AND warehouse_id=:w
                       AND batch_code IS NOT DISTINCT FROM :c
                     FOR UPDATE
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id), "c": batch_code_norm},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"stock slot missing for item={item_id}, wh={warehouse_id}, code={batch_code_norm}")
    return int(row["sid"]), int(row["q"])


async def _apply_stock_delta(
    session: AsyncSession,
    *,
    stock_id: int,
    delta: int,
) -> None:
    await session.execute(
        text("UPDATE stocks SET qty = qty + :d WHERE id = :sid"),
        {"d": int(delta), "sid": int(stock_id)},
    )


# ----------------------------
# date rules (receipt-side enrichment)
# ----------------------------
async def _resolve_and_validate_dates_for_inbound(
    *,
    session: AsyncSession,
    item_id: int,
    delta: int,
    batch_code_norm: Optional[str],
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    """
    当前行为保持不变：
    - 仅当 delta>0 且 batch_code 非空时才解析日期
    - 若两者都缺，则补 production_date=today()
    - 通过 resolve_batch_dates_for_item() 做业务规则补全
    - 校验 exp>=prod
    - 若 batch_code 为 None，则强制 dates=None
    """
    pd = production_date
    ed = expiry_date

    if delta > 0 and batch_code_norm is not None:
        if pd is None and ed is None:
            pd = pd or date.today()

        pd, ed = await resolve_batch_dates_for_item(
            session=session,
            item_id=item_id,
            production_date=pd,
            expiry_date=ed,
        )

        if ed is not None and pd is not None:
            if ed < pd:
                raise ValueError(f"expiry_date({ed}) < production_date({pd})")

    if batch_code_norm is None:
        pd = None
        ed = None

    return pd, ed


# ----------------------------
# main impl
# ----------------------------
async def adjust_impl(  # noqa: C901
    *,
    session: AsyncSession,
    item_id: int,
    delta: int,
    reason: Union[str, MovementType],
    ref: str,
    ref_line: Optional[Union[int, str]] = None,
    occurred_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
    batch_code: Optional[str] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    warehouse_id: int,
    trace_id: Optional[str],
    lot_id: Optional[int],  # ✅ Phase 3 新增（影子维度）
    utc_now: Callable[[], datetime],
    ensure_batch_dict_fn: Callable[
        [AsyncSession, int, int, str, Optional[date], Optional[date], datetime], Awaitable[None]
    ],
) -> Dict[str, Any]:
    """
    批次增减（单一真实来源 stocks）

    Phase 3:
    - lot_id 仅透传至 ledger_writer
    - 不参与幂等判断
    """

    reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
    rl = int(ref_line) if ref_line is not None else 1
    ts = occurred_at or utc_now()

    allow_zero = _meta_bool(meta, "allow_zero_delta_ledger")
    sub_reason = _meta_str(meta, "sub_reason")

    # --- delta==0 gate (keep behavior) ---
    if delta == 0 and not allow_zero:
        return {"idempotent": True, "applied": False}

    if delta == 0 and allow_zero and not sub_reason:
        raise ValueError("delta==0 记账必须提供 meta.sub_reason（例如 COUNT_ADJUST）")

    # --- batch semantics ---
    requires_batch = await _item_requires_batch(session, item_id=int(item_id))
    bc_norm = _norm_batch_code(batch_code)

    if requires_batch and not bc_norm:
        raise ValueError("批次受控商品必须指定 batch_code。")

    # --- date resolve (keep behavior) ---
    production_date, expiry_date = await _resolve_and_validate_dates_for_inbound(
        session=session,
        item_id=int(item_id),
        delta=int(delta),
        batch_code_norm=bc_norm,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # ---------- 幂等检查（仍基于 batch_code_key） ----------
    if await _idem_hit_by_batch_key(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code_norm=bc_norm,
        reason=reason_val,
        ref=str(ref),
        ref_line=int(rl),
    ):
        return {"idempotent": True, "applied": False}

    # --- ensure batch dict (only for inbound with batch_code) ---
    if delta > 0 and bc_norm is not None:
        await ensure_batch_dict_fn(
            session,
            int(warehouse_id),
            int(item_id),
            str(bc_norm),
            production_date,
            expiry_date,
            ts,
        )

    # --- ensure stocks slot exists ---
    await _ensure_stock_slot_exists(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code_norm=bc_norm,
    )

    # --- lock stock slot ---
    stock_id, before_qty = await _lock_stock_slot_for_update(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code_norm=bc_norm,
    )

    # --- compute after qty (keep behavior) ---
    if delta == 0:
        new_qty = before_qty
    else:
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock: before={before_qty}, delta={delta}")

    # ✅ Phase 3: lot_id 仅透传，不参与幂等
    await write_ledger(
        session=session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,
        reason=reason_val,
        sub_reason=sub_reason,
        delta=int(delta),
        after_qty=new_qty,
        ref=str(ref),
        ref_line=int(rl),
        occurred_at=ts,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
        lot_id=lot_id,
    )

    if delta != 0:
        await _apply_stock_delta(session, stock_id=int(stock_id), delta=int(delta))

    meta_out: Dict[str, Any] = dict(meta or {})
    if trace_id:
        meta_out.setdefault("trace_id", trace_id)

    return {
        "stock_id": int(stock_id),
        "before": int(before_qty),
        "delta": int(delta),
        "after": int(new_qty),
        "reason": str(reason_val),
        "ref": str(ref),
        "ref_line": int(rl),
        "meta": meta_out,
        "occurred_at": ts.isoformat(),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
