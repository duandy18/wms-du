#!/usr/bin/env python3
import argparse
import asyncio
import json
import time
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 复用你项目现有的 DB / Celery
from app.db.session import async_session_maker
from app.worker import celery


FIX_NONE_SET = {"", "none", "null", "None", "NULL"}


def _fix_payload(payload: Dict[str, Any], strip_from_state: bool, force_to_state: Optional[str]) -> Dict[str, Any]:
    p = dict(payload or {})
    if strip_from_state:
        fs = str(p.get("from_state", "") or "")
        if fs.strip() in FIX_NONE_SET:
            p.pop("from_state", None)
    if force_to_state:
        p["to_state"] = force_to_state
    return p


async def _iter_illegal(
    session: AsyncSession,
    platform: Optional[str],
    shop_id: Optional[str],
    order_no: Optional[str],
    limit: int,
) -> list[dict]:
    # 只抓取 ILLEGAL_TRANSITION
    sql = """
    SELECT id, platform, shop_id, order_no, idempotency_key, payload_json
    FROM event_error_log
    WHERE error_code = 'ILLEGAL_TRANSITION'
      AND (:platform IS NULL OR platform = :platform)
      AND (:shop_id IS NULL OR shop_id = :shop_id)
      AND (:order_no IS NULL OR order_no = :order_no)
    ORDER BY id DESC
    LIMIT :limit
    """
    rows = (await session.execute(text(sql), {
        "platform": platform, "shop_id": shop_id, "order_no": order_no, "limit": limit
    })).mappings().all()
    return [dict(r) for r in rows]


async def replay(
    platform: Optional[str],
    shop_id: Optional[str],
    order_no: Optional[str],
    strip_from_state: bool,
    force_to_state: Optional[str],
    qps: float,
    limit: int,
    dry_run: bool,
) -> None:
    count = 0
    async with async_session_maker() as session:  # type: AsyncSession
        items = await _iter_illegal(session, platform, shop_id, order_no, limit)
        if not items:
            print("No ILLEGAL_TRANSITION rows matched.")
            return

        interval = 0.0 if qps <= 0 else 1.0 / qps
        for row in items:
            p = row["platform"]
            s = row["shop_id"]
            payload = row["payload_json"] or {}
            fixed = _fix_payload(payload, strip_from_state, force_to_state)

            task_kwargs = {"platform": p, "shop_id": s, "payload": fixed}
            print(f"[{row['id']}] -> queue=events.{p}.{s} order={row['order_no']} dry_run={dry_run}")
            if not dry_run:
                # 发到与线上一致的任务入口
                r = celery.send_task("wms.process_event", kwargs=task_kwargs)
                try:
                    result = r.get(timeout=60)
                    print("  result:", result)
                except Exception as e:
                    print("  raised:", e)

            count += 1
            if interval > 0:
                time.sleep(interval)

    print(f"Done. Replayed: {count} rows.")


def main():
    ap = argparse.ArgumentParser(description="Replay ILLEGAL_TRANSITION events with optional payload fixes.")
    ap.add_argument("--platform", help="filter by platform")
    ap.add_argument("--shop-id", help="filter by shop_id")
    ap.add_argument("--order-no", help="filter by order_no")
    ap.add_argument("--limit", type=int, default=50, help="max rows to replay")
    ap.add_argument("--qps", type=float, default=2.0, help="send speed (tasks per second)")
    ap.add_argument("--strip-from-state", action="store_true",
                    help="treat empty/'none'/'null' from_state as None and remove it from payload")
    ap.add_argument("--force-to-state", help="force payload.to_state to this value (e.g. PAID)")
    ap.add_argument("--dry-run", action="store_true", help="plan only, do not actually send tasks")
    args = ap.parse_args()

    asyncio.run(
        replay(
            platform=args.platform,
            shop_id=args.shop_id,
            order_no=args.order_no,
            strip_from_state=args.strip_from_state,
            force_to_state=args.force_to_state,
            qps=args.qps,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
