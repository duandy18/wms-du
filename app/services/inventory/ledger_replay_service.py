# app/services/inventory/ledger_replay_service.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LedgerReplayService:
    """
    Ledger Replay Engine
    --------------------
    从 ledger 逐事件重放库存，模拟 stocks 变化。

    Phase 4 提示：
    - 当主维度切到 lot_id 后，slot key 应切换到 (wh,item,lot_id)（并处理 NONE 槽位）。
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
            SELECT id, occurred_at, reason, delta, warehouse_id, item_id, batch_code
            FROM stock_ledger
            WHERE occurred_at >= :t1 AND occurred_at <= :t2
            ORDER BY occurred_at ASC, id ASC;
        """
        )

        rows = (await session.execute(sql, {"t1": time_from, "t2": time_to})).mappings().all()

        slot: dict[tuple[int, int, str | None], int] = {}
        timeline: list[dict[str, Any]] = []

        for e in rows:
            k = (int(e["warehouse_id"]), int(e["item_id"]), e["batch_code"])
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
                    "batch_code": k[2],
                }
            )

        return timeline
