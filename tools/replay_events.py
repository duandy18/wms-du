#!/usr/bin/env python3
"""
Phase 2.8 · 事件重放 CLI（过滤/演练/审计）
支持：
  --status            PENDING,DLQ（默认支持多值，用逗号分隔）
  --any-status        忽略状态过滤（与 --status 互斥）
  --key-prefix        只重放以该前缀开头的 key（如 S1:）
  --since/--until     时间窗（基于 occurred_at；格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）
  --limit             最大匹配条数（默认 100）
  --requeue-to        将匹配到的事件批量改为 PENDING 或 DLQ 再处理
  --force-fail        让 handler 人为抛错，用于快速制造 DLQ 场景
  --dry-run           只打印 matched，不改状态、不执行业务
"""

import os
import sys
import argparse
import asyncio
from datetime import datetime
from typing import Optional, Sequence, List

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.events.models_event_store import EventRow
from app.events.replayer import audit_repair  # 审计事件


DATABASE_URL = os.getenv("DATABASE_URL")


def _parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    raise SystemExit(f"[replay] Invalid time format: {s}")


async def _default_handler(payload: Optional[dict]) -> None:
    """
    默认 handler：不做任何副作用。
    你可以换成领域修复逻辑（入库/上架/出库的幂等补偿）。
    """
    return None


async def replay_filtered(
    session,
    *,
    topic: str,
    statuses: Optional[Sequence[str]],
    any_status: bool,
    limit: int,
    key_prefix: Optional[str],
    since: Optional[datetime],
    until: Optional[datetime],
    requeue_to: Optional[str],
    handler,
    dry_run: bool,
    force_fail: bool,
) -> int:
    conds = [EventRow.topic == topic]
    if not any_status and statuses:
        conds.append(EventRow.status.in_(tuple(s.upper() for s in statuses)))
    if key_prefix:
        conds.append(EventRow.key.like(f"{key_prefix}%"))
    if since:
        conds.append(EventRow.occurred_at >= since)
    if until:
        conds.append(EventRow.occurred_at < until)

    stmt = select(EventRow).where(and_(*conds)).order_by(EventRow.id.asc()).limit(limit)
    rows: List[EventRow] = (await session.execute(stmt)).scalars().all()

    print(f"matched={len(rows)}")

    if not rows:
        return 0

    # 需要“回入队”的场景（如把 CONSUMED/DLQ 改回 PENDING 再跑）
    if requeue_to in {"PENDING", "DLQ"} and not dry_run:
        ids = [r.id for r in rows]
        await session.execute(
            update(EventRow)
            .where(EventRow.id.in_(ids))
            .values(status=requeue_to, last_error=None if requeue_to == "PENDING" else EventRow.last_error)
        )
        await session.commit()
        # 重新加载最新状态（避免后续逻辑读到旧对象）
        rows = (await session.execute(stmt)).scalars().all()

    if dry_run:
        for r in rows:
            print(f"[dry-run] id={r.id} key={r.key} status={r.status} attempts={r.attempts}")
        return len(rows)

    # 重放处理
    ok, fail = 0, 0
    for r in rows:
        try:
            if force_fail:
                raise RuntimeError("forced by --force-fail")
            await handler(r.payload if isinstance(r.payload, dict) else None)
            await session.execute(
                update(EventRow)
                .where(EventRow.id == r.id)
                .values(status="CONSUMED", attempts=r.attempts + 1, last_error=None)
            )
            # 审计：记录一次 repair 事件（闭环可追溯）
            await audit_repair(session, r, note="auto repair by replay")
            ok += 1
        except Exception as e:
            await session.execute(
                update(EventRow)
                .where(EventRow.id == r.id)
                .values(status="DLQ", attempts=r.attempts + 1, last_error=str(e))
            )
            fail += 1

    await session.commit()
    print(f"replayed ok={ok} fail={fail}")
    return len(rows)


async def main():
    parser = argparse.ArgumentParser(description="Replay events with filters / requeue / audit")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--status", default="PENDING,DLQ", help="comma list, e.g. PENDING or PENDING,DLQ")
    parser.add_argument("--any-status", action="store_true", help="ignore status filter")
    parser.add_argument("--key-prefix")
    parser.add_argument("--since", help="YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--until", help="YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--requeue-to", choices=["PENDING", "DLQ"])
    parser.add_argument("--force-fail", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DATABASE_URL:
        print("DATABASE_URL is not set", file=sys.stderr)
        raise SystemExit(2)

    statuses = None
    if not args.any_status and args.status:
        statuses = [s.strip().upper() for s in args.status.split(",") if s.strip()]
        if not statuses:
            statuses = ["PENDING", "DLQ"]

    since = _parse_time(args.since)
    until = _parse_time(args.until)

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        handler = _default_handler
        await replay_filtered(
            session,
            topic=args.topic,
            statuses=statuses,
            any_status=args.any_status,
            limit=args.limit,
            key_prefix=args.key_prefix,
            since=since,
            until=until,
            requeue_to=args.requeue_to,
            handler=handler,
            dry_run=args.dry_run,
            force_fail=args.force_fail,
        )

if __name__ == "__main__":
    asyncio.run(main())
