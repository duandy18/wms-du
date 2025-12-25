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
    批次增减（单一真实来源 stocks）；全量支持日期推导：

    - 入库(delta>0)：
          必须提供 batch_code；
          必须有日期（prod 或 exp），否则自动兜底 + 推导；
          若批次主档缺失，自动创建；
          批次主档日期缺失时可由本次补齐（但我们当前策略是不覆盖已有日期）。

    - 出库(delta<0)：
          只需要 batch_code；
          日期无需提供（不会改变批次元数据）。

    - 幂等：
          按 (warehouse_id, item_id, batch_code, reason, ref, ref_line) 判断。
    """
    reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
    rl = int(ref_line) if ref_line is not None else 1
    ts = occurred_at or utc_now()

    # ---------- 基础校验 ----------
    if delta == 0:
        return {"idempotent": True, "applied": False}

    if not batch_code or not str(batch_code).strip():
        raise ValueError("批次操作必须指定 batch_code。")
    batch_code = str(batch_code).strip()

    # 入库 & 盘盈：必须有日期（prod 或 exp），并做统一推算
    if delta > 0:
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

    # ---------- 幂等 ----------
    idem = await session.execute(
        text(
            """
            SELECT 1
              FROM stock_ledger
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND batch_code   = :c
               AND reason       = :r
               AND ref          = :ref
               AND ref_line     = :rl
             LIMIT 1
            """
        ),
        {
            "w": int(warehouse_id),
            "i": item_id,
            "c": batch_code,
            "r": reason_val,
            "ref": ref,
            "rl": rl,
        },
    )
    if idem.scalar_one_or_none() is not None:
        return {"idempotent": True, "applied": False}

    # ---------- 入库：确保批次主档存在 ----------
    if delta > 0:
        await ensure_batch_dict_fn(
            session,
            int(warehouse_id),
            item_id,
            batch_code,
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
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {
            "i": item_id,
            "w": int(warehouse_id),
            "c": batch_code,
        },
    )

    # ---------- 加锁读取当前库存 ----------
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id AS sid, qty AS q
                      FROM stocks
                     WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c
                     FOR UPDATE
                    """
                ),
                {"i": item_id, "w": int(warehouse_id), "c": batch_code},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(
            f"stock slot missing for item={item_id}, wh={warehouse_id}, code={batch_code}"
        )

    stock_id, before_qty = int(row["sid"]), int(row["q"])
    new_qty = before_qty + int(delta)
    if new_qty < 0:
        raise ValueError(f"insufficient stock: before={before_qty}, delta={delta}")

    # ---------- 写台账（带上 trace_id + 日期） ----------
    await write_ledger(
        session=session,
        warehouse_id=int(warehouse_id),
        item_id=item_id,
        batch_code=batch_code,
        reason=reason_val,
        delta=int(delta),
        after_qty=new_qty,
        ref=ref,
        ref_line=rl,
        occurred_at=ts,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # ---------- 更新余额 ----------
    await session.execute(
        text("UPDATE stocks SET qty = qty + :d WHERE id = :sid"),
        {"d": int(delta), "sid": stock_id},
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
