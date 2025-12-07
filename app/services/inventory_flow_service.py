# app/services/inventory_flow_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryFlowService:
    """
    Inventory Flow Graph
    --------------------
    将库存事件（ledger）构造成 "节点 + 边" 的有向图结构。

    节点：
      warehouse -> item -> batch -> ledger_event

    边：
      warehouse -> item
      item -> batch
      batch -> ledger_event

    前端可渲染可视化图。
    """

    @staticmethod
    async def build_graph(
        session: AsyncSession,
        *,
        time_from: str,
        time_to: str,
    ) -> Dict[str, Any]:
        # 1. 拉 ledger 事件
        sql = text(
            """
            SELECT id, occurred_at, reason, delta, after_qty,
                   warehouse_id, item_id, batch_code, trace_id, ref
            FROM stock_ledger
            WHERE occurred_at >= :t1 AND occurred_at <= :t2
            ORDER BY occurred_at ASC, id ASC
        """
        )

        rows = (await session.execute(sql, {"t1": time_from, "t2": time_to})).mappings().all()
        events = [dict(r) for r in rows]

        # 2. 构造 nodes
        nodes = []
        edges = []

        wh_set = set()
        item_set = set()
        batch_set = set()

        for e in events:
            wid = e["warehouse_id"]
            iid = e["item_id"]
            bc = e["batch_code"]

            # warehouse node
            if wid not in wh_set:
                wh_set.add(wid)
                nodes.append({"id": f"wh-{wid}", "type": "warehouse", "label": f"WH {wid}"})

            # item node
            if (wid, iid) not in item_set:
                item_set.add((wid, iid))
                nodes.append({"id": f"item-{wid}-{iid}", "type": "item", "label": f"Item {iid}"})
                edges.append({"from": f"wh-{wid}", "to": f"item-{wid}-{iid}"})

            # batch node
            if (wid, iid, bc) not in batch_set:
                batch_set.add((wid, iid, bc))
                nodes.append(
                    {"id": f"batch-{wid}-{iid}-{bc}", "type": "batch", "label": f"Batch {bc}"}
                )
                edges.append({"from": f"item-{wid}-{iid}", "to": f"batch-{wid}-{iid}-{bc}"})

            # event node
            eid = f"event-{e['id']}"
            nodes.append(
                {
                    "id": eid,
                    "type": "event",
                    "label": f"{e['reason']} [{e['delta']}]",
                    "detail": e,
                }
            )
            edges.append(
                {
                    "from": f"batch-{wid}-{iid}-{bc}",
                    "to": eid,
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "count": len(events),
        }
