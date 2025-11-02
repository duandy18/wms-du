# app/services/ledger_writer.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---- 简单的缓存，避免反复命中 information_schema/pg_constraint ----
_COL_CACHE: dict[tuple[str, str], bool] = {}
_FLAG_CACHE: dict[str, bool] = {}  # e.g. "ledger_uq_threecol" -> bool


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


async def _has_threecol_uq(session: AsyncSession) -> bool:
    """
    是否存在 (reason,ref,ref_line) 三列唯一约束（历史版本）。
    通过名字快速探测；若名字不一致，可按列集合探测（此处先走名字分支，足够覆盖现状）。
    """
    key = "ledger_uq_threecol"
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'stock_ledger'
               AND c.contype = 'u'
               AND c.conname IN (
                 'uq_stock_ledger_reason_ref_refline',       -- 常见历史名
                 'uq_ledger_reason_ref_refline'              -- 另一路并行历史名
               )
             LIMIT 1
            """
        )
    )
    ok = row.first() is not None
    _FLAG_CACHE[key] = ok
    return ok


async def _advisory_lock(session: AsyncSession, key: str) -> None:
    """事务级互斥：对同一 key 串行化写入。"""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


async def write_ledger(
    session: AsyncSession,
    *,
    stock_id: int | None,
    item_id: int,
    reason: str,
    delta: int,
    after_qty: int,
    ref: str | None,
    ref_line: int | str | None,  # 允许保留签名，但在原子SQL路径中会忽略该值
    occurred_at: datetime | None = None,
    extra: Optional[dict[str, Any]] = None,
) -> int:
    """
    原子写入一条台账，返回 ledger.id。
    - 探测唯一键形态：三列 (reason,ref,ref_line) vs. 四列 (reason,ref,ref_line,stock_id)
    - 对应选择锁与 MAX(ref_line) 的计算维度，避免三列口径下跨 stock_id 撞线
    - 动态检测 extra 列，有则写，无则忽略
    - :reason/:ref 显式 CAST 为 VARCHAR，消除 asyncpg 类型歧义
    """
    ts = occurred_at or datetime.now(UTC)
    reason = (reason or "").upper()
    ref = (ref or "") or None
    sid = int(stock_id or 0)
    has_extra = await _has_column(session, "stock_ledger", "extra")
    has_3uq = await _has_threecol_uq(session)

    # 参数显式类型转换片段
    reason_cast = "CAST(:reason AS VARCHAR(32))"
    ref_cast = "CAST(:ref AS VARCHAR(64))"

    # 选择锁维度 & WHERE 维度
    if has_3uq:
        # 三列口径：锁(reason,ref)，在该维度下全局递增 ref_line
        await _advisory_lock(session, f"ledger:{reason}:{ref or ''}")
        where_dim = f"reason = {reason_cast} AND ref = {ref_cast}"
    else:
        # 四列或无 UQ：锁(reason,ref,stock_id)，在该维度下递增
        if sid > 0:
            await _advisory_lock(session, f"ledger:{reason}:{ref or ''}:{sid}")
            where_dim = f"reason = {reason_cast} AND ref = {ref_cast} AND stock_id = :sid"
        else:
            # 极少数无 stock_id 的写法，退化为(reason,ref)
            await _advisory_lock(session, f"ledger:{reason}:{ref or ''}")
            where_dim = f"reason = {reason_cast} AND ref = {ref_cast}"

    # 组装 INSERT ... SELECT 原子写入
    if sid > 0:
        if has_extra:
            sql = text(
                f"""
                INSERT INTO stock_ledger
                  (stock_id, item_id, reason, ref, ref_line, delta, occurred_at, after_qty, extra)
                SELECT
                  :sid, :item, {reason_cast}, {ref_cast},
                  COALESCE(MAX(ref_line), 0) + 1,
                  :delta, :ts, :after, CAST(:extra AS jsonb)
                  FROM stock_ledger
                 WHERE {where_dim}
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
                f"""
                INSERT INTO stock_ledger
                  (stock_id, item_id, reason, ref, ref_line, delta, occurred_at, after_qty)
                SELECT
                  :sid, :item, {reason_cast}, {ref_cast},
                  COALESCE(MAX(ref_line), 0) + 1,
                  :delta, :ts, :after
                  FROM stock_ledger
                 WHERE {where_dim}
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
    else:
        # 无 stock_id — 少见场景，ref_line 固定为 1
        if has_extra:
            sql = text(
                """
                INSERT INTO stock_ledger
                  (item_id, reason, ref, ref_line, delta, occurred_at, after_qty, extra)
                VALUES
                  (:item, CAST(:reason AS VARCHAR(32)), CAST(:ref AS VARCHAR(64)), 1, :delta, :ts, :after, CAST(:extra AS jsonb))
                RETURNING id
                """
            )
            params = {
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
                  (item_id, reason, ref, ref_line, delta, occurred_at, after_qty)
                VALUES
                  (:item, CAST(:reason AS VARCHAR(32)), CAST(:ref AS VARCHAR(64)), 1, :delta, :ts, :after)
                RETURNING id
                """
            )
            params = {
                "item": item_id,
                "reason": reason,
                "ref": ref,
                "delta": int(delta),
                "ts": ts,
                "after": int(after_qty),
            }

    r = await session.execute(sql, params)
    return int(r.scalar_one())
