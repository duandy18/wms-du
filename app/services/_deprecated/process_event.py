from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.models.enums import MovementType
from app.services._event_writer import EventWriter
from app.services.stock_service import StockService


class EventProcessor:
    """
    事件处理器（主程序版）：
    - 只做“事件 → 领域指令”路由；
    - 禁止业务直 SQL，库存动作一律走 StockService/领域服务；
    - 审计统一写入 event_log。

    Phase 3.6：
      - 使用 v2 StockService.adjust(warehouse_id, item_id, batch_code, ...)；
      - 为每个事件生成 trace_id，并写入 event_log.meta.trace_id。
    """

    def __init__(self) -> None:
        self.audit = EventWriter(source="event-processor")
        self.stock = StockService()

    async def _resolve_warehouse_id(self, session: AsyncSession, location_id: int) -> Optional[int]:
        """通过 location_id 查 warehouse_id（兼容旧 payload）"""
        row = await session.execute(
            text("SELECT warehouse_id FROM locations WHERE id=:loc_id"),
            {"loc_id": int(location_id)},
        )
        val = row.scalar_one_or_none()
        return int(val) if val is not None else None

    async def handle(self, session: AsyncSession, *, event: dict):
        topic = (event or {}).get("topic")
        payload: dict[str, Any] = (event or {}).get("payload") or {}

        # 每个事件独立一个 trace
        trace = new_trace(f"event:{topic or 'UNKNOWN'}")

        if topic == "inventory.adjust":
            # v2 adjust：需要 warehouse_id + batch_code
            item_id = int(payload["item_id"])
            loc_id = int(payload["location_id"])
            delta = int(payload["delta"])
            batch_code = payload.get("batch_code")
            expiry_date = payload.get("expiry_date")
            reason_raw = payload.get("reason")

            if batch_code is None or str(batch_code).strip() == "":
                raise ValueError("inventory.adjust requires batch_code in v2 model")

            wh_id = await self._resolve_warehouse_id(session, loc_id)
            if wh_id is None:
                raise ValueError(f"no warehouse_id for location_id={loc_id}")

            movement = MovementType(reason_raw) if isinstance(reason_raw, str) else reason_raw

            async with session.begin():
                res = await self.stock.adjust(
                    session=session,
                    item_id=item_id,
                    warehouse_id=wh_id,
                    delta=delta,
                    reason=movement,
                    ref=payload.get("ref", f"EVT-{payload.get('id', '')}"),
                    ref_line=payload.get("ref_line", 1),
                    batch_code=batch_code,
                    expiry_date=expiry_date,
                    trace_id=trace.trace_id,
                )

            await self.audit.write_json(
                session,
                level="INFO",
                message={
                    "handled": topic,
                    "delta": res.get("delta"),
                    "after": res.get("after"),
                },
                meta={"trace_id": trace.trace_id},
            )
            return res

        # 其它 topic 可在此扩展（例如 inbound.receive / outbound.commit 等）
        await self.audit.write_json(
            session,
            level="INFO",
            message={"ignored": topic or "UNKNOWN"},
            meta={"trace_id": trace.trace_id},
        )
        return {"ignored": True, "topic": topic}
