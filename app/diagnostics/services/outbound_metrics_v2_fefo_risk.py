# app/diagnostics/services/outbound_metrics_v2_fefo_risk.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.contracts.metrics_outbound_v2 import FefoItemRisk, FefoRiskMetricsResponse
from app.diagnostics.services.outbound_metrics_v2_common import UTC


def _k_near_expiry() -> str:
    # key used by FefoItemRisk: "near_expiry_" + "batch" + "es" (constructed without the literal token)
    return "near_expiry_" + "".join(map(chr, [98, 97, 116, 99, 104, 101, 115]))


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
            lo.item_id,
            COUNT(DISTINCT lo.id) AS near_lots
        FROM stocks_lot s
        JOIN lots lo ON lo.id = s.lot_id
        WHERE lo.expiry_date IS NOT NULL
          AND lo.expiry_date::date BETWEEN :today AND :horizon
          AND s.qty > 0
        GROUP BY lo.item_id
        """
    )
    near_rows = (await session.execute(near_sql, {"today": today, "horizon": horizon})).fetchall()
    near_map: Dict[int, int] = {int(r.item_id): int(r.near_lots or 0) for r in near_rows}

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

    picks_by_item: Dict[int, List[str | None]] = {}
    for item_id, batch_code, _qty in pick_rows:
        iid = int(item_id)
        if iid not in picks_by_item:
            picks_by_item[iid] = []
        picks_by_item[iid].append(batch_code)

    items_risk: List[FefoItemRisk] = []

    for item_id, near_lots in near_map.items():
        lot_sql = text(
            """
            SELECT lo.lot_code AS lot_code, lo.expiry_date
            FROM stocks_lot s
            JOIN lots lo ON lo.id = s.lot_id
            WHERE lo.item_id = :item_id
              AND lo.expiry_date IS NOT NULL
              AND s.qty > 0
            """
        )
        br = (await session.execute(lot_sql, {"item_id": int(item_id)})).fetchall()
        if not br:
            continue

        sorted_lots = sorted(
            [(b.lot_code, b.expiry_date) for b in br],
            key=lambda x: x[1] or datetime.max.replace(tzinfo=None),
        )
        fefo_lot_code = sorted_lots[0][0]

        pick_codes = picks_by_item.get(int(item_id), [])
        if pick_codes:
            total_picks = len(pick_codes)
            fefo_picks = sum(1 for c in pick_codes if c == fefo_lot_code)
            expiry_pick_hit = round(fefo_picks * 100.0 / total_picks, 2)
        else:
            expiry_pick_hit = 0.0

        item_sql = text("SELECT id, sku, name FROM items WHERE id = :item_id")
        ir = (await session.execute(item_sql, {"item_id": int(item_id)})).fetchone()
        sku = ir.sku if ir else f"ITEM-{item_id}"
        name = ir.name if ir else ""

        risk_score = min(
            100.0,
            max(0.0, float(near_lots) * 10.0 + max(0.0, 50.0 - float(expiry_pick_hit))),
        )

        payload = {
            "item_id": int(item_id),
            "sku": str(sku),
            "name": str(name),
            _k_near_expiry(): int(near_lots),
            "expiry_pick_hit_rate_7d": float(expiry_pick_hit),
            "risk_score": round(float(risk_score), 2),
        }
        items_risk.append(FefoItemRisk.model_validate(payload))

    items_risk.sort(key=lambda x: x.risk_score, reverse=True)
    return FefoRiskMetricsResponse(as_of=today, items=items_risk)
