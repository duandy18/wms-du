# app/services/snapshot_item_detail.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def query_item_detail(
    session: AsyncSession,
    *,
    item_id: int,
    pools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    返回单个商品的“仓 + 批次”明细。

    ✅ 主线 B：避免 NULL 吞数据
    - join batches 时使用 IS NOT DISTINCT FROM，确保 batch_code=NULL 的槽位也能匹配到 batches(NULL) 行（如果存在）。
    """
    _pools = [p.upper() for p in (pools or [])] or ["MAIN"]  # 预留参数，不过滤
    _ = _pools

    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    s.item_id,
                    i.name AS item_name,
                    s.warehouse_id,
                    w.name AS warehouse_name,
                    s.batch_code,
                    s.qty,
                    b.production_date,
                    b.expiry_date
                FROM stocks AS s
                JOIN items AS i
                  ON i.id = s.item_id
                JOIN warehouses AS w
                  ON w.id = s.warehouse_id
                LEFT JOIN batches AS b
                  ON b.item_id      = s.item_id
                 AND b.warehouse_id = s.warehouse_id
                 AND b.batch_code IS NOT DISTINCT FROM s.batch_code
                WHERE s.item_id = :item_id
                  AND s.qty <> 0
                ORDER BY s.warehouse_id, s.batch_code
                """
                ),
                {"item_id": item_id},
            )
        )
        .mappings()
        .all()
    )

    if not rows:
        return {
            "item_id": item_id,
            "item_name": "",
            "totals": {
                "on_hand_qty": 0,
                "reserved_qty": 0,
                "available_qty": 0,
            },
            "slices": [],
        }

    first = rows[0]
    item_name = first["item_name"]

    today = datetime.now(UTC).date()
    near_delta = timedelta(days=30)

    slices: List[Dict[str, Any]] = []
    total_on_hand = 0

    for r in rows:
        qty = int(r["qty"] or 0)
        if qty == 0:
            continue

        production_date = r.get("production_date")
        expiry_date = r.get("expiry_date")

        near = False
        if isinstance(expiry_date, date):
            if expiry_date >= today and (expiry_date - today) <= near_delta:
                near = True

        pool = "MAIN"

        slice_rec: Dict[str, Any] = {
            "warehouse_id": int(r["warehouse_id"]),
            "warehouse_name": r["warehouse_name"],
            "pool": pool,
            "batch_code": r["batch_code"],
            "production_date": production_date,
            "expiry_date": expiry_date,
            "on_hand_qty": qty,
            "reserved_qty": 0,
            "available_qty": qty,
            "near_expiry": near,
            "is_top": False,
        }
        slices.append(slice_rec)
        total_on_hand += qty

    if slices:
        ranked = sorted(
            list(enumerate(slices)),
            key=lambda kv: kv[1]["on_hand_qty"],
            reverse=True,
        )
        for idx, _rec in ranked[:2]:
            slices[idx]["is_top"] = True

    totals = {
        "on_hand_qty": total_on_hand,
        "reserved_qty": 0,
        "available_qty": total_on_hand,
    }

    return {
        "item_id": item_id,
        "item_name": item_name,
        "totals": totals,
        "slices": slices,
    }
