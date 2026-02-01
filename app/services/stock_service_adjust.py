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

# 第三阶段护栏（保守版）：
# 仅拦截“明确属于历史假批次占位符”的码，避免误伤可能被测试/业务当作真实批次码的字符串（例如 IDEM）
_FAKE_BATCH_CODES = {"NOEXP", "NEAR", "FAR"}


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


def _norm_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


def _batch_key(batch_code: Optional[str]) -> str:
    bc = _norm_batch_code(batch_code)
    return bc if bc is not None else "__NULL_BATCH__"


async def _item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    """
    临时事实派生（本窗口主线）：
    - items.has_shelf_life == True  => requires_batch == True
    - 其他（False/NULL）            => requires_batch == False

    重要：item 不存在时不要在这里提前 raise，
    让后续写库触发 FK（测试依赖此行为）。
    """
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
    utc_now: Callable[[], datetime],
    ensure_batch_dict_fn: Callable[
        [AsyncSession, int, int, str, Optional[date], Optional[date], datetime], Awaitable[None]
    ],
) -> Dict[str, Any]:
    """
    批次增减（单一真实来源 stocks）

    ✅ 无批次槽位支持（唯一主线）：
    - requires_batch=true  => batch_code 必须非空
    - requires_batch=false => batch_code 允许为 NULL（表示“无批次”）

    ✅ 入库日期推导的兼容口径（为保持既有测试/行为）：
    - 只要 delta>0 且 batch_code 非空，就会自动兜底并推导日期
    - batch_code 为 NULL（无批次槽位）时不推导日期

    ✅ 第三阶段护栏（防历史假批次回流，保守版）：
    - 对 requires_batch=false 的商品：
        若 batch_code 是明确假批次占位符（NOEXP/NEAR/FAR），则归一为 NULL
      注意：不再把 IDEM 当作假码，避免误伤现有测试/业务批次码。
    """
    reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
    rl = int(ref_line) if ref_line is not None else 1
    ts = occurred_at or utc_now()

    allow_zero = _meta_bool(meta, "allow_zero_delta_ledger")
    sub_reason = _meta_str(meta, "sub_reason")

    if delta == 0 and not allow_zero:
        return {"idempotent": True, "applied": False}

    if delta == 0 and allow_zero and not sub_reason:
        raise ValueError("delta==0 记账必须提供 meta.sub_reason（例如 COUNT_ADJUST）")

    requires_batch = await _item_requires_batch(session, item_id=int(item_id))
    bc_norm = _norm_batch_code(batch_code)

    # ✅ 第三阶段护栏：非批次商品遇到明确假码 → 归一为 NULL
    if not requires_batch and bc_norm is not None:
        if bc_norm.upper() in _FAKE_BATCH_CODES:
            bc_norm = None

    if requires_batch and not bc_norm:
        raise ValueError("批次受控商品必须指定 batch_code。")

    # 入库/盘盈：只要 batch_code 非空，就推导日期（兼容原测试口径）
    if delta > 0 and bc_norm is not None:
        if production_date is None and expiry_date is None:
            production_date = production_date or date.today()

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session=session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        if expiry_date is not None and production_date is not None:
            if expiry_date < production_date:
                raise ValueError(f"expiry_date({expiry_date}) < production_date({production_date})")

    # 无批次槽位：不推导/不写日期
    if bc_norm is None:
        production_date = None
        expiry_date = None

    # ---------- 幂等：用 batch_code_key 对齐 NULL 语义 ----------
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
            "ck": _batch_key(bc_norm),
            "r": reason_val,
            "ref": ref,
            "rl": rl,
        },
    )
    if idem.scalar_one_or_none() is not None:
        return {"idempotent": True, "applied": False}

    # ---------- 入库：确保批次主档存在（仅 batch_code 非空时才有意义） ----------
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

    # ---------- 确保 stocks 槽位存在 ----------
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

    # ---------- 加锁读取当前库存（支持 NULL batch_code） ----------
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
                {"i": int(item_id), "w": int(warehouse_id), "c": bc_norm},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"stock slot missing for item={item_id}, wh={warehouse_id}, code={bc_norm}")

    stock_id, before_qty = int(row["sid"]), int(row["q"])

    if delta == 0:
        new_qty = before_qty
    else:
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock: before={before_qty}, delta={delta}")

    await write_ledger(
        session=session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,  # ✅ may be NULL
        reason=reason_val,
        sub_reason=sub_reason,
        delta=int(delta),
        after_qty=new_qty,
        ref=ref,
        ref_line=rl,
        occurred_at=ts,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    if delta != 0:
        await session.execute(
            text("UPDATE stocks SET qty = qty + :d WHERE id = :sid"),
            {"d": int(delta), "sid": int(stock_id)},
        )

    meta_out: Dict[str, Any] = dict(meta or {})
    if trace_id:
        meta_out.setdefault("trace_id", trace_id)

    return {
        "stock_id": stock_id,
        "before": before_qty,
        "delta": int(delta),
        "after": new_qty,
        "reason": reason_val,
        "ref": ref,
        "ref_line": rl,
        "meta": meta_out,
        "occurred_at": ts.isoformat(),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
