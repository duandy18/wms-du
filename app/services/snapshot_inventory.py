# app/services/snapshot_inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def query_inventory_snapshot(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Snapshot /inventory 主列表（事实视图）

    lot-world 正确实现：
    - 不依赖 expiry_date 字段
    - 使用 created_at + shelf_life 动态计算
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
                    i.spec      AS spec,
                    i.brand     AS brand,
                    i.category  AS category,

                    s.warehouse_id,
                    l.lot_code AS batch_code,
                    s.qty,

                    -- ✅ 正确 interval 写法
                    CASE
                      WHEN l.item_expiry_policy_snapshot = 'REQUIRED'
                       AND l.item_shelf_life_value_snapshot IS NOT NULL
                      THEN
                        l.created_at +
                        CASE l.item_shelf_life_unit_snapshot
                          WHEN 'DAY' THEN l.item_shelf_life_value_snapshot * interval '1 day'
                          WHEN 'WEEK' THEN l.item_shelf_life_value_snapshot * interval '7 day'
                          WHEN 'MONTH' THEN l.item_shelf_life_value_snapshot * interval '1 month'
                          WHEN 'YEAR' THEN l.item_shelf_life_value_snapshot * interval '1 year'
                        END
                      ELSE NULL
                    END AS expiry_date,

                    (
                        SELECT ib.barcode
                        FROM item_barcodes AS ib
                        WHERE ib.item_id = s.item_id
                          AND ib.active = true
                        ORDER BY ib.is_primary DESC, ib.id ASC
                        LIMIT 1
                    ) AS main_barcode

                FROM stocks_lot AS s
                JOIN items AS i
                  ON i.id = s.item_id
                LEFT JOIN lots AS l
                  ON l.id = s.lot_id
                WHERE s.qty <> 0
                ORDER BY s.item_id, s.warehouse_id, l.lot_code NULLS FIRST
                """
                )
            )
        )
        .mappings()
        .all()
    )

    today = datetime.now(UTC).date()
    near_delta = timedelta(days=30)

    result: List[Dict[str, Any]] = []
    for r in rows:
        qty = int(r["qty"] or 0)

        expiry_dt = r.get("expiry_date")

        # ✅ 统一类型
        expiry_date: Optional[date]
        if isinstance(expiry_dt, datetime):
            expiry_date = expiry_dt.date()
        elif isinstance(expiry_dt, date):
            expiry_date = expiry_dt
        else:
            expiry_date = None

        near_expiry = False
        days_to_expiry = None

        if expiry_date:
            days_to_expiry = int((expiry_date - today).days)
            if expiry_date >= today and (expiry_date - today) <= near_delta:
                near_expiry = True

        result.append(
            {
                "item_id": int(r["item_id"]),
                "item_name": r["item_name"],
                "item_code": r["item_code"],
                "spec": r["spec"],
                "brand": r["brand"],
                "category": r["category"],
                "main_barcode": r["main_barcode"],
                "warehouse_id": int(r["warehouse_id"]),
                "batch_code": r["batch_code"],
                "lot_code": r["batch_code"],
                "qty": qty,
                "expiry_date": expiry_date,
                "near_expiry": near_expiry,
                "days_to_expiry": days_to_expiry,
            }
        )

    return result


async def query_inventory_snapshot_paged(
    session: AsyncSession,
    *,
    q: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
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
