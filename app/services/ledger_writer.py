# app/services/ledger_writer.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---- 简单的列存在性缓存，避免每次都查 information_schema ----
_COL_CACHE: dict[tuple[str, str], bool] = {}


async def _has_column(session: AsyncSession, table: str, column: str) -> bool:
    key = (table, column)
    if key in _COL_CACHE:
        return _COL_CACHE[key]
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name=:tbl
               AND column_name=:col
             LIMIT 1
            """
        ),
        {"tbl": table, "col": column},
    )
    ok = row.first() is not None
    _COL_CACHE[key] = ok
    return ok


async def _advisory_lock(session: AsyncSession, reason: str, ref: str, stock_id: int) -> None:
    """同一 (reason, ref, stock_id) 维度下的事务级互斥锁，避免并发撞线。"""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"ledger:{reason}:{ref}:{stock_id}"},
    )


async def write_ledger(
    session: AsyncSession,
    *,
    stock_id: int | None,
    item_id: int,
    reason: str,
    delta: int,
    after_qty: int,
    ref: str | None,
    ref_line: int | str | None,
    occurred_at: datetime | None = None,
    extra: Optional[dict[str, Any]] = None,  # 运行时可选；若表无该列则忽略
) -> int:
    """
    原子写入一条台账，返回 ledger.id。
    - 同维度 (reason, ref, stock_id) 使用 advisory 锁串行化；
    - 在 INSERT 的 SELECT 子句里原子计算 ref_line = COALESCE(MAX(ref_line),0)+1；
    - 兼容 stock_ledger 是否存在 extra 列（动态列集）；
    - UTC 时间、after_qty 等保持你现有口径。
    """
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    sid = int(stock_id or 0)

    has_extra = await _has_column(session, "stock_ledger", "extra")

    # 带 stock_id 的常规路径（PUTAWAY/INBOUND/OUTBOUND/COUNT）：原子 INSERT ... SELECT
    if sid > 0:
        await _advisory_lock(session, reason, ref or "", sid)

        if has_extra:
            sql = text(
                """
                INSERT INTO stock_ledger
                  (stock_id, item_id, reason, ref, ref_line, delta, occurred_at, after_qty, extra)
                SELECT
                  :sid, :item, :reason, :ref,
                  COALESCE(MAX(ref_line), 0) + 1,
                  :delta, :ts, :after, CAST(:extra AS jsonb)
                  FROM stock_ledger
                 WHERE reason = :reason AND ref = :ref AND stock_id = :sid
                RETURNING id
                """
            )
            params = {
                "sid": sid,
                "item": item_id,
                "reason": reason,
                "ref": ref,
                "delta": int(delta),
                "ts": ts,
                "after": int(after_qty),
                "extra": extra or {},
            }
        else:
            sql = text(
                """
                INSERT INTO stock_ledger
                  (stock_id, item_id, reason, ref, ref_line, delta, occurred_at, after_qty)
                SELECT
                  :sid, :item, :reason, :ref,
                  COALESCE(MAX(ref_line), 0) + 1,
                  :delta, :ts, :after
                  FROM stock_ledger
                 WHERE reason = :reason AND ref = :ref AND stock_id = :sid
                RETURNING id
                """
            )
            params = {
                "sid": sid,
                "item": item_id,
                "reason": reason,
                "ref": ref,
                "delta": int(delta),
                "ts": ts,
                "after": int(after_qty),
            }

        r = await session.execute(sql, params)
        return int(r.scalar_one())

    # 极少场景（无 stock_id）——给 ref_line=1；保持与历史兼容
    if has_extra:
        sql = text(
            """
            INSERT INTO stock_ledger
              (item_id, reason, ref, ref_line, delta, occurred_at, after_qty, extra)
            VALUES
              (:item, :reason, :ref, :rline, :delta, :ts, :after, CAST(:extra AS jsonb))
            RETURNING id
            """
        )
        params = {
            "item": item_id,
            "reason": reason,
            "ref": ref,
            "rline": 1,
            "delta": int(delta),
            "ts": ts,
            "after": int(after_qty),
            "extra": extra or {},
        }
    else:
        sql = text(
            """
            INSERT INTO stock_ledger
              (item_id, reason, ref, ref_line, delta, occurred_at, after_qty)
            VALUES
              (:item, :reason, :ref, :rline, :delta, :ts, :after)
            RETURNING id
            """
        )
        params = {
            "item": item_id,
            "reason": reason,
            "ref": ref,
            "rline": 1,
            "delta": int(delta),
            "ts": ts,
            "after": int(after_qty),
        }

    r = await session.execute(sql, params)
    return int(r.scalar_one())
