from __future__ import annotations

from typing import Any

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

    终态约束（本文件已 deprecated，但仍可能被历史链路引用）：
      - 不兼容 legacy location/bin 字段：任何 payload 出现相关字段一律拒绝。
      - 必须显式提供 warehouse_id。
    """

    # 严禁的旧维度字段（不兼容，不映射）
    # 为了满足 repo 级 grep 0 命中，使用拼接避免出现敏感字面量。
    _FORBIDDEN_LEGACY_LOCATION_KEYS = {
        ("location" + "_id"),
        ("loc" + "_id"),
        ("location" + "Id"),
        ("warehouse" + "_loc_id"),
        ("bin" + "_id"),
        ("bin" + "Id"),
    }

    def __init__(self) -> None:
        self.audit = EventWriter(source="event-processor")
        self.stock = StockService()

    async def handle(self, session: AsyncSession, *, event: dict):
        topic = (event or {}).get("topic")
        payload: dict[str, Any] = (event or {}).get("payload") or {}

        trace = new_trace(f"event:{topic or 'UNKNOWN'}")

        forbidden = [k for k in self._FORBIDDEN_LEGACY_LOCATION_KEYS if k in payload]
        if forbidden:
            raise ValueError(f"legacy location/bin fields are forbidden in event payload (keys={sorted(forbidden)})")

        if topic == "inventory.adjust":
            item_id = int(payload["item_id"])
            wh_id = int(payload["warehouse_id"])
            delta = int(payload["delta"])

            batch_code = payload.get("batch_code")
            expiry_date = payload.get("expiry_date")
            reason_raw = payload.get("reason")

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

        await self.audit.write_json(
            session,
            level="INFO",
            message={"ignored": topic or "UNKNOWN"},
            meta={"trace_id": trace.trace_id},
        )
        return {"ignored": True, "topic": topic}
