# app/services/ledger_writer.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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


async def _next_ref_line(session: AsyncSession, *, reason: str, ref: str, stock_id: int) -> int:
    """估算下一个 ref_line：同 (reason, ref, stock_id) 维度下的 MAX+1。"""
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0) + 1
              FROM stock_ledger
             WHERE reason = :reason
               AND ref    = :ref
               AND stock_id = :stock_id
            """
        ),
        {"reason": reason, "ref": ref, "stock_id": stock_id},
    )
    v = row.scalar()
    return int(v or 1)


def _to_refline_int(ref_line: int | str | None) -> int:
    if isinstance(ref_line, int):
        return ref_line
    import zlib
    return int(zlib.crc32(str(ref_line).encode("utf-8")) & 0x7FFFFFFF)


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
    写入一条台账，返回 ledger.id（UTC + after_qty，唯一键 (reason, ref, ref_line, stock_id)）。

    收口要点：
    - 使用 advisory lock 锁定 (reason,ref,stock_id) 维度，降低并发冲突概率；
    - INSERT 放在 SAVEPOINT（begin_nested）中，若撞唯一键 -> 仅回滚到保存点，自增 ref_line 重试；
    - 根据 stock_ledger 是否存在 extra 列，动态选择 INSERT 列集，避免 CI 上 undefined column。
    """
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    sid = int(stock_id or 0)

    # ref_line 规范化：若传入字符串做稳定哈希；若为空则稍后用 MAX+1
    rline: Optional[int] = _to_refline_int(ref_line) if ref_line is not None else None

    # 对于带 stock_id 的写入，加事务级 advisory 锁；若未给定 ref_line，先估算一次
    if sid > 0:
        await _advisory_lock(session, reason, ref or "", sid)
        if not rline or rline <= 0:
            rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
        else:
            exist = await session.execute(
                text(
                    """
                    SELECT 1
                      FROM stock_ledger
                     WHERE reason=:reason AND ref=:ref
                       AND stock_id=:stock_id AND ref_line=:ref_line
                    """
                ),
                {"reason": reason, "ref": ref, "stock_id": sid, "ref_line": int(rline)},
            )
            if exist.first():
                rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
    else:
        rline = rline or 1

    # --- 动态决定是否写 extra 列 ---
    has_extra = await _has_column(session, "stock_ledger", "extra")

    if has_extra:
        cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at", "after_qty", "extra"]
        vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts", ":after", "CAST(:extra AS jsonb)"]
    else:
        cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at", "after_qty"]
        vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts", ":after"]

    if sid > 0:
        cols.insert(0, "stock_id")
        vals.insert(0, ":sid")

    sql = text(f"INSERT INTO stock_ledger ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id")

    params = {
        "sid": sid if sid > 0 else None,
        "item": item_id,
        "reason": reason,
        "ref": ref,
        "rline": int(rline),
        "delta": int(delta),
        "ts": ts,
        "after": int(after_qty),
    }
    if has_extra:
        params["extra"] = extra or {}

    # SAVEPOINT + 重试（处理唯一约束冲突）
    for attempt in range(5):
        try:
            async with session.begin_nested():  # SAVEPOINT
                res = await session.execute(sql, params)
                new_id = res.scalar_one()
            return int(new_id)
        except IntegrityError as ie:
            msg = (str(getattr(ie, "orig", ie)) or "").lower()
            if sid > 0 and (
                "uq_ledger_reason_ref_refline_stock" in msg
                or "uq_stock_ledger_reason_ref_refline" in msg
                or "duplicate" in msg
                or "unique" in msg
            ):
                params["rline"] = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
                continue
            raise

    raise RuntimeError(
        f"write_ledger failed after retries: reason={reason}, ref={ref}, stock_id={sid}"
    )
