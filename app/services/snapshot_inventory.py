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

    ✅ Phase 2 硬规则：禁止“隐性汇总”
    - 展示维度：至少 warehouse_id + item_id + batch_code（每个批次必须分行可审计）
    - 库存事实：来自 stocks（不做二次按 item 聚合）
    - 主数据字段：来自 items（1:1 join，不放大）
    - 主条码：仅 active=true；primary 优先，否则最小 id（稳定且可解释）
    - 日期相关：后端统一 UTC 计算，前端不推导

    ✅ 主线 B：避免 NULL 吞数据
    - join batches 时使用 IS NOT DISTINCT FROM，确保 batch_code=NULL 的槽位也能匹配到 batches(NULL) 行（如果存在）。
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
                    i.uom       AS uom,
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
                 AND b.batch_code IS NOT DISTINCT FROM s.batch_code
                WHERE s.qty <> 0
                ORDER BY s.item_id, s.warehouse_id, s.batch_code
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
        expiry_date = r.get("expiry_date")

        near_expiry = False
        days_to_expiry = None
        if isinstance(expiry_date, date):
            days_to_expiry = int((expiry_date - today).days)
            if expiry_date >= today and (expiry_date - today) <= near_delta:
                near_expiry = True

        result.append(
            {
                "item_id": int(r["item_id"]),
                "item_name": r["item_name"],
                "item_code": r["item_code"],
                "uom": r["uom"],
                "spec": r["spec"],
                "brand": r["brand"],
                "category": r["category"],
                "main_barcode": r["main_barcode"],
                "warehouse_id": int(r["warehouse_id"]),
                "batch_code": r["batch_code"],
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
