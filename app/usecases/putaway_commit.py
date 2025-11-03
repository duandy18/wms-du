# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports import StockOpsPort, EventLogPort

class PutawayCommitUseCase:
    def __init__(self, stock_ops: StockOpsPort, event_log: EventLogPort) -> None:
        self.stock_ops = stock_ops
        self.event_log = event_log

    async def execute(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        scan_ref: str,
    ) -> Dict[str, Any]:
        # 1) 库存搬运（双腿）
        res = await self.stock_ops.transfer(
            session=session,
            item_id=item_id,
            src_location_id=from_location_id,
            dst_location_id=to_location_id,
            qty=qty,
            reason="PUTAWAY",
            ref=scan_ref,
        )

        # 2) 事件入库（message 用纯文本 scan_ref，保持与测试一致）
        occurred_at = datetime.now(timezone.utc)
        ev_id = await self.event_log.log(
            session=session,
            source="scan_putaway_commit",
            message=scan_ref,
            occurred_at=occurred_at,
        )
        await session.commit()

        return {
            "scan_ref": scan_ref,
            "ref": scan_ref,
            "source": "scan_putaway_commit",
            "occurred_at": occurred_at.isoformat(),
            "committed": True,
            "event_id": ev_id,
            "result": res,
        }
