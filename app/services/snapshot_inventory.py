# app/services/snapshot_inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def query_inventory_snapshot(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    返回扁平化的 inventory 列表，每行包含：
      - item_id
      - item_name
      - total_qty
      - top2_locations（字段名沿用旧结构，语义为“前两条明细”）
      - earliest_expiry（最早过期日）
      - near_expiry（在 30 天内即将过期）
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    s.item_id,
                    i.name AS item_name,
                    s.warehouse_id,
                    s.batch_code,
                    s.qty,
                    b.expiry_date AS expiry_date
                FROM stocks AS s
                JOIN items AS i
                  ON i.id = s.item_id
                LEFT JOIN batches AS b
                  ON b.item_id      = s.item_id
                 AND b.warehouse_id = s.warehouse_id
                 AND b.batch_code   = s.batch_code
                WHERE s.qty <> 0
                ORDER BY s.item_id, s.warehouse_id, s.batch_code
                """
                )
            )
        )
        .mappings()
        .all()
    )

    by_item: Dict[int, Dict[str, Any]] = {}
    today = datetime.now(UTC).date()
    near_delta = timedelta(days=30)

    for r in rows:
        item_id = int(r["item_id"])
        item_name = r["item_name"]
        wh_id = int(r["warehouse_id"])
        batch_code = r["batch_code"]
        qty = int(r["qty"] or 0)
        expiry_date = r.get("expiry_date")

        if item_id not in by_item:
            by_item[item_id] = {
                "item_id": item_id,
                "item_name": item_name,
                "total_qty": 0,
                "buckets": [],
                "earliest_expiry": None,
                "near_expiry": False,
            }

        rec = by_item[item_id]
        rec["total_qty"] += qty
        rec["buckets"].append(
            {
                "warehouse_id": wh_id,
                "batch_code": batch_code,
                "qty": qty,
                "expiry_date": expiry_date,
            }
        )

        if isinstance(expiry_date, date):
            if rec["earliest_expiry"] is None or expiry_date < rec["earliest_expiry"]:
                rec["earliest_expiry"] = expiry_date
            if expiry_date >= today and (expiry_date - today) <= near_delta:
                rec["near_expiry"] = True

    result: List[Dict[str, Any]] = []
    for _item_id, rec in by_item.items():
        buckets = sorted(rec["buckets"], key=lambda b: b["qty"], reverse=True)
        top2 = [
            {
                "warehouse_id": b["warehouse_id"],
                "batch_code": b["batch_code"],
                "qty": b["qty"],
            }
            for b in buckets[:2]
        ]
        result.append(
            {
                "item_id": rec["item_id"],
                "item_name": rec["item_name"],
                "total_qty": rec["total_qty"],
                "top2_locations": top2,
                "earliest_expiry": rec["earliest_expiry"],
                "near_expiry": rec["near_expiry"],
            }
        )

    result.sort(key=lambda r: r["item_id"])
    return result


async def query_inventory_snapshot_paged(
    session: AsyncSession,
    *,
    q: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    基于 query_inventory_snapshot 的结果做内存分页 / 模糊搜索。
    """
    full = await query_inventory_snapshot(session)

    if q:
        q_lower = q.lower()
        full = [r for r in full if q_lower in (r["item_name"] or "").lower()]

    total = len(full)
    rows = full[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": rows,
    }
