from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.obs.metrics import wms_inventory_mismatch_total

CONSISTENCY_SQL = """
WITH ledger_sum AS (
  SELECT stock_id, SUM(delta_qty) AS qty_delta
  FROM stock_ledger
  GROUP BY stock_id
),
joined AS (
  SELECT s.id AS stock_id, s.qty, COALESCE(l.qty_delta,0) AS delta
  FROM stocks s
  LEFT JOIN ledger_sum l ON l.stock_id = s.id
)
SELECT stock_id, qty, delta, (qty - delta) as diff
FROM joined
WHERE qty <> delta;
"""


async def check_and_optionally_fix(
    session: AsyncSession, auto_fix: bool = False, dry_run: bool = True
):
    rows = (await session.execute(text(CONSISTENCY_SQL))).mappings().all()
    mismatches = 0
    for r in rows:
        mismatches += 1
        wms_inventory_mismatch_total.labels("stocks_vs_ledger").inc()
        if auto_fix:
            if not dry_run:
                await session.execute(
                    text("UPDATE stocks SET qty=:delta WHERE id=:sid"),
                    {"delta": r["delta"], "sid": r["stock_id"]},
                )
    if auto_fix and not dry_run:
        await session.commit()
    return mismatches
