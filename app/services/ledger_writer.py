# app/services/ledger_writer.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


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
    extra: Optional[dict[str, Any]] = None,  # 允许透传额外信息（如需要）
) -> int:
    """
    写入一条台账，返回 ledger.id（UTC + after_qty，唯一键 (reason, ref, ref_line, stock_id)）。

    收口要点：
    - 使用 advisory lock 锁定 (reason,ref,stock_id) 维度，降低并发冲突概率；
    - INSERT 放在 SAVEPOINT（begin_nested）中，若撞唯一键 -> 仅回滚到保存点，自增 ref_line 重试；
    - 最多重试 5 次（极端场景仍能前进），避免事务进入 aborted 状态。
    """
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    sid = int(stock_id or 0)

    # 统一准备 ref_line：优先使用传入 int；若传入字符串做稳定哈希；若为空则稍后用 MAX+1
    rline: Optional[int] = _to_refline_int(ref_line) if ref_line is not None else None

    # 构造 INSERT 语句（保留你原有列集/顺序）
    cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at", "after_qty", "extra"]
    vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts", ":after", "CAST(:extra AS jsonb)"]
    if sid > 0:
        cols.insert(0, "stock_id")
        vals.insert(0, ":sid")
    sql = text(f"INSERT INTO stock_ledger ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id")

    # 对于带 stock_id 的写入，加事务级 advisory 锁；若未给定 ref_line，先估算一次
    if sid > 0:
        await _advisory_lock(session, reason, ref or "", sid)
        if not rline or rline <= 0:
            rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
        else:
            # 若指定 ref_line 已存在于该 (reason,ref,stock_id) 下，则切到 MAX+1
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
        rline = rline or 1  # 无 stock_id 维度时，给个稳定起点

    # 统一参数
    params = {
        "sid": sid if sid > 0 else None,
        "item": item_id,
        "reason": reason,
        "ref": ref,
        "rline": int(rline),
        "delta": int(delta),
        "ts": ts,
        "after": int(after_qty),
        "extra": extra or {},
    }

    # SAVEPOINT + 重试（处理唯一约束冲突）
    for attempt in range(5):
        try:
            async with session.begin_nested():  # SAVEPOINT（不会把外层事务打成 aborted）
                res = await session.execute(sql, params)
                new_id = res.scalar_one()
            return int(new_id)
        except IntegrityError as ie:
            msg = (str(getattr(ie, "orig", ie)) or "").lower()
            # 命中唯一键冲突（不同项目历史可能有两个名字，统一兜住）
            if sid > 0 and (
                "uq_ledger_reason_ref_refline_stock" in msg
                or "uq_stock_ledger_reason_ref_refline" in msg
                or "duplicate" in msg
                or "unique" in msg
            ):
                # 自增 ref_line，再试一次（避免与其它并发 INSERT 撞线）
                params["rline"] = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
                continue
            # 非唯一键问题，向上抛
            raise

    # 超过重试次数仍失败（极端并发/异常），抛出明确错误
    raise RuntimeError(
        f"write_ledger failed after retries: reason={reason}, ref={ref}, stock_id={sid}"
    )
