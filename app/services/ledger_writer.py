# app/services/ledger_writer.py
from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _advisory_lock(session: AsyncSession, reason: str, ref: str, stock_id: int) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                          {"k": f"ledger:{reason}:{ref}:{stock_id}"})


async def _next_ref_line(session: AsyncSession, *, reason: str, ref: str, stock_id: int) -> int:
    row = await session.execute(
        text("""
            SELECT COALESCE(MAX(ref_line), 0) + 1
            FROM stock_ledger
            WHERE reason=:reason AND ref=:ref AND stock_id=:stock_id
        """),
        {"reason": reason, "ref": ref, "stock_id": stock_id},
    )
    return int(row.scalar() or 1)


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
) -> int:
    """写入台账，返回 ledger.id（UTC + after_qty，幂等键(reason,ref,stock_id,ref_line)）。"""
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    rline = _to_refline_int(ref_line) if ref_line is not None else None
    sid = int(stock_id or 0)

    cols = ["item_id", "reason", "ref", "ref_line", "delta", "occurred_at", "after_qty"]
    vals = [":item", ":reason", ":ref", ":rline", ":delta", ":ts", ":after"]
    if sid > 0:
        cols.insert(0, "stock_id")
        vals.insert(0, ":sid")

    sql = text(f"INSERT INTO stock_ledger ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id")

    if sid > 0:
        await _advisory_lock(session, reason, ref or "", sid)
        if not rline or rline <= 0:
            rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
        else:
            exist = await session.execute(
                text("""SELECT 1 FROM stock_ledger
                        WHERE reason=:reason AND ref=:ref AND stock_id=:stock_id AND ref_line=:ref_line"""),
                {"reason": reason, "ref": ref, "stock_id": sid, "ref_line": int(rline)},
            )
            if exist.first():
                rline = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
    else:
        rline = rline or 1

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

    try:
        res = await session.execute(sql, params)
        return int(res.scalar_one())
    except IntegrityError as e:
        msg = (str(getattr(e, "orig", e)) or "").lower()
        if sid > 0 and ("uq_ledger_reason_ref_refline_stock" in msg or "uq_stock_ledger_reason_ref_refline" in msg):
            params["rline"] = await _next_ref_line(session, reason=reason, ref=ref or "", stock_id=sid)
            res = await session.execute(sql, params)
            return int(res.scalar_one())
        raise
