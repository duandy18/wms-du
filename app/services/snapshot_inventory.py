# app/services/snapshot_inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def query_inventory_snapshot(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Snapshot /inventory 主列表（事实视图）：

    - 库存事实：完全来自 stocks 聚合（不受主数据 join 影响）
    - 主数据字段：来自 items（1:1 join，不放大）
    - 主条码：仅 active=true；primary 优先，否则最小 id（稳定且可解释）
    - 日期相关：后端统一 UTC 计算，前端不推导
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    s.item_id,
                    i.name      AS item_name,
                    i.sku       AS item_code,
                    i.unit      AS uom,
                    i.spec      AS spec,
                    i.brand     AS brand,
                    i.category  AS category,

                    s.warehouse_id,
                    s.batch_code,
                    s.qty,

                    b.expiry_date AS expiry_date,

                    (
                        SELECT ib.barcode
                        FROM item_barcodes AS ib
                        WHERE ib.item_id = s.item_id
                          AND ib.active = true
                        ORDER BY ib.is_primary DESC, ib.id ASC
                        LIMIT 1
                    ) AS main_barcode

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
        qty = int(r["qty"] or 0)
        expiry_date = r.get("expiry_date")

        if item_id not in by_item:
            by_item[item_id] = {
                "item_id": item_id,
                "item_name": r["item_name"],
                "item_code": r["item_code"],
                "uom": r["uom"],
                "spec": r["spec"],
                "brand": r["brand"],
                "category": r["category"],
                "main_barcode": r["main_barcode"],
                "total_qty": 0,
                "buckets": [],
                "earliest_expiry": None,
                "near_expiry": False,
                "days_to_expiry": None,
            }

        rec = by_item[item_id]
        rec["total_qty"] += qty
        rec["buckets"].append(
            {
                "warehouse_id": int(r["warehouse_id"]),
                "batch_code": r["batch_code"],
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
    for rec in by_item.values():
        buckets = sorted(rec["buckets"], key=lambda b: b["qty"], reverse=True)
        top2 = [
            {
                "warehouse_id": b["warehouse_id"],
                "batch_code": b["batch_code"],
                "qty": b["qty"],
            }
            for b in buckets[:2]
        ]

        if isinstance(rec["earliest_expiry"], date):
            rec["days_to_expiry"] = int((rec["earliest_expiry"] - today).days)

        result.append(
            {
                "item_id": rec["item_id"],
                "item_name": rec["item_name"],
                "item_code": rec["item_code"],
                "uom": rec["uom"],
                "spec": rec["spec"],
                "brand": rec["brand"],
                "category": rec["category"],
                "main_barcode": rec["main_barcode"],
                "total_qty": rec["total_qty"],
                "top2_locations": top2,
                "earliest_expiry": rec["earliest_expiry"],
                "near_expiry": rec["near_expiry"],
                "days_to_expiry": rec["days_to_expiry"],
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
    内存分页 + 模糊搜索（item_name / item_code）
    """
    full = await query_inventory_snapshot(session)

    if q:
        q_lower = q.lower()
        full = [
            r
            for r in full
            if q_lower in (r.get("item_name") or "").lower()
            or q_lower in (r.get("item_code") or "").lower()
        ]

    total = len(full)
    rows = full[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": rows,
    }
