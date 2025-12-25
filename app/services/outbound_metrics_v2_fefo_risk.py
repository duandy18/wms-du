# app/services/outbound_metrics_v2_fefo_risk.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import FefoItemRisk, FefoRiskMetricsResponse
from app.services.outbound_metrics_v2_common import UTC


async def load_fefo_risk(
    session: AsyncSession,
    *,
    days: int = 7,
) -> FefoRiskMetricsResponse:
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=30)
    since_day = today - timedelta(days=days)

    near_sql = text(
        """
        SELECT
            b.item_id,
            count(*) AS near_batches
        FROM batches b
        WHERE b.expiry_date IS NOT NULL
          AND b.expiry_date::date BETWEEN :today AND :horizon
        GROUP BY b.item_id
        """
    )
    near_rows = (await session.execute(near_sql, {"today": today, "horizon": horizon})).fetchall()
    near_map: Dict[int, int] = {int(r.item_id): int(r.near_batches or 0) for r in near_rows}

    if not near_map:
        return FefoRiskMetricsResponse(as_of=today, items=[])

    pick_sql = text(
        """
        SELECT
            l.item_id,
            l.batch_code,
            abs(l.delta) AS qty
        FROM stock_ledger l
        WHERE l.delta < 0
          AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
          AND (l.occurred_at AT TIME ZONE 'utc')::date BETWEEN :since_day AND :today
          AND l.item_id = ANY(:item_ids)
        """
    )
    item_ids = list(near_map.keys())
    pick_rows = (
        await session.execute(
            pick_sql, {"since_day": since_day, "today": today, "item_ids": item_ids}
        )
    ).fetchall()

    picks_by_item: Dict[int, List[str]] = {}
    for item_id, batch_code, qty in pick_rows:
        if item_id not in picks_by_item:
            picks_by_item[item_id] = []
        picks_by_item[item_id].append(batch_code)

    items_risk: List[FefoItemRisk] = []

    for item_id, near_batches in near_map.items():
        bsql = text(
            """
            SELECT batch_code, expiry_date
            FROM batches
            WHERE item_id = :item_id
              AND expiry_date IS NOT NULL
            """
        )
        br = (await session.execute(bsql, {"item_id": item_id})).fetchall()
        if not br:
            continue

        sorted_batches = sorted(
            [(b.batch_code, b.expiry_date) for b in br],
            key=lambda x: x[1] or datetime.max.replace(tzinfo=None),
        )
        fefo_batch = sorted_batches[0][0]

        pick_codes = picks_by_item.get(item_id, [])
        if pick_codes:
            total_picks = len(pick_codes)
            fefo_picks = sum(1 for c in pick_codes if c == fefo_batch)
            fefo_hit = round(fefo_picks * 100.0 / total_picks, 2)
        else:
            fefo_hit = 0.0

        item_sql = text("SELECT id, sku, name FROM items WHERE id = :item_id")
        ir = (await session.execute(item_sql, {"item_id": item_id})).fetchone()
        sku = ir.sku if ir else f"ITEM-{item_id}"
        name = ir.name if ir else ""

        risk_score = min(
            100.0,
            max(0.0, near_batches * 10.0 + max(0.0, 50.0 - fefo_hit)),
        )

        items_risk.append(
            FefoItemRisk(
                item_id=item_id,
                sku=sku,
                name=name,
                near_expiry_batches=near_batches,
                fefo_hit_rate_7d=fefo_hit,
                risk_score=round(risk_score, 2),
            )
        )

    items_risk.sort(key=lambda x: x.risk_score, reverse=True)
    return FefoRiskMetricsResponse(as_of=today, items=items_risk)
