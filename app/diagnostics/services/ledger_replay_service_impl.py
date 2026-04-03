# app/diagnostics/services/ledger_replay_service_impl.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LedgerReplayService:
    """
    Ledger Replay Engine
    --------------------
    从 ledger 逐事件重放库存，模拟 stocks_lot 变化。

    Phase 3 终态（lot-only）：
    - slot key 必须切到 (wh, item, lot_id)
    - batch_code 仅用于展示（lots.lot_code），不参与 slot key
    """

    @staticmethod
    async def replay(
        session: AsyncSession,
        *,
        time_from: str,
        time_to: str,
    ) -> List[Dict[str, Any]]:
        sql = text(
            """
            SELECT
              l.id,
              l.occurred_at,
              l.reason,
              l.delta,
              l.warehouse_id,
              l.item_id,
              l.lot_id,
              lo.lot_code AS batch_code
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE l.occurred_at >= :t1 AND l.occurred_at <= :t2
            ORDER BY l.occurred_at ASC, l.id ASC;
        """
        )

        rows = (await session.execute(sql, {"t1": time_from, "t2": time_to})).mappings().all()

        slot: dict[tuple[int, int, int], int] = {}
        timeline: list[dict[str, Any]] = []

        for e in rows:
            k = (int(e["warehouse_id"]), int(e["item_id"]), int(e["lot_id"]))
            slot.setdefault(k, 0)
            before = slot[k]
            after = before + int(e["delta"])
            slot[k] = after

            timeline.append(
                {
                    "id": e["id"],
                    "occurred_at": e["occurred_at"],
                    "reason": e["reason"],
                    "delta": e["delta"],
                    "before": before,
                    "after": after,
                    "warehouse_id": k[0],
                    "item_id": k[1],
                    "lot_id": k[2],
                    # 展示码：lots.lot_code（可能为 NULL）
                    "batch_code": e.get("batch_code"),
                }
            )

        return timeline
