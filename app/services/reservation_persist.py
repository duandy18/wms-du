# app/services/reservation_persist.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def persist(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    ref: str,
    lines: List[Dict[str, Any]],
    expire_at: Optional[int] = None,  # minutes
    trace_id: Optional[str] = None,  # Phase 3.7-A：链路主键
) -> Dict[str, Any]:
    """
    幂等建/改一张 reservation + 明细。

    语义：
      - 使用 (platform, shop_id, warehouse_id, ref) 作为业务键；
      - 若不存在，则 INSERT 一条 status='open' 的头记录；
      - 若已存在，则保持 status='open'，更新 expire_at（若传入）与 updated_at；
      - reservation_lines：
          * 按 ref_line=1..N 重新写入：
              - 已有同 (reservation_id, ref_line) 则更新 item_id/qty；
              - 没有则插入新行，consumed_qty 初始为 0；
          * 不会删除多余 ref_line。

    Phase 3.7-A：trace_id 规则
      - effective_trace_id = trace_id or ref
      - 新插入的头记录总会写入 trace_id = effective_trace_id；
      - 对已存在记录，在 UPDATE 阶段执行：
          trace_id = COALESCE(trace_id, :trace_id)
        只为旧数据填补空值，不覆盖已有非空 trace_id。
    """
    effective_trace_id = trace_id or ref

    created_at = datetime.now(timezone.utc)
    updated_at = created_at

    expire_dt: Optional[datetime] = None
    if expire_at is not None:
        expire_dt = created_at + timedelta(minutes=int(expire_at))

    insert_res_sql = text(
        """
        INSERT INTO reservations (
            platform, shop_id, warehouse_id, ref,
            status, created_at, updated_at, expire_at, trace_id
        )
        VALUES (
            :platform, :shop_id, :warehouse_id, :ref,
            'open', :created_at, :updated_at, :expire_at, :trace_id
        )
        ON CONFLICT (platform, shop_id, warehouse_id, ref)
        DO NOTHING
        RETURNING id
        """
    )
    key_params = {
        "platform": platform,
        "shop_id": shop_id,
        "warehouse_id": warehouse_id,
        "ref": ref,
        "created_at": created_at,
        "updated_at": updated_at,
        "expire_at": expire_dt,
        "trace_id": effective_trace_id,
    }
    inserted = await session.execute(insert_res_sql, key_params)
    reservation_id = inserted.scalar_one_or_none()

    if reservation_id is None:
        row = await session.execute(
            text(
                """
                SELECT id
                FROM reservations
                WHERE platform = :platform
                  AND shop_id = :shop_id
                  AND warehouse_id = :warehouse_id
                  AND ref = :ref
                """
            ),
            {
                "platform": platform,
                "shop_id": shop_id,
                "warehouse_id": warehouse_id,
                "ref": ref,
            },
        )
        res = row.first()
        if res is None:
            raise RuntimeError("Failed to resolve reservation ID after concurrent insert conflict.")

        reservation_id = int(res[0])
        await session.execute(
            text(
                """
                UPDATE reservations
                   SET updated_at = :updated_at,
                       expire_at  = COALESCE(:expire_at, expire_at),
                       trace_id   = COALESCE(trace_id, :trace_id)
                 WHERE id = :rid
                """
            ),
            {
                "rid": reservation_id,
                "updated_at": updated_at,
                "expire_at": expire_dt,
                "trace_id": effective_trace_id,
            },
        )

    line_now = datetime.now(timezone.utc)

    update_line_sql = text(
        """
        UPDATE reservation_lines
           SET item_id    = :item,
               qty        = :qty,
               updated_at = :now
         WHERE reservation_id = :rid
           AND ref_line       = :ref_line
        """
    )
    insert_line_sql = text(
        """
        INSERT INTO reservation_lines (
            reservation_id, ref_line,
            item_id, qty, consumed_qty,
            created_at, updated_at
        )
        VALUES (
            :rid, :ref_line,
            :item, :qty, 0,
            :now, :now
        )
        """
    )

    for idx, ln in enumerate(lines or (), start=1):
        item_id = int(ln["item_id"])
        qty = int(ln["qty"])
        line_params = {
            "rid": reservation_id,
            "ref_line": idx,
            "item": item_id,
            "qty": qty,
            "now": line_now,
        }
        updated = await session.execute(update_line_sql, line_params)
        if updated.rowcount == 0:
            await session.execute(insert_line_sql, line_params)

    return {
        "status": "OK",
        "reservation_id": reservation_id,
    }
