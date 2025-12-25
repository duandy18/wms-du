# app/services/receive_task_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receive_task import ReceiveTask
from app.schemas.receive_task import OrderReturnLineIn
from app.services.inbound_service import InboundService

from app.services.receive_task_commit import commit as _commit
from app.services.receive_task_create import create_for_order as _create_for_order
from app.services.receive_task_create import create_for_po as _create_for_po
from app.services.receive_task_query import get_with_lines as _get_with_lines
from app.services.receive_task_scan import record_scan as _record_scan

UTC = timezone.utc

NOEXP_BATCH_CODE = "NOEXP"


class ReceiveTaskService:
    """
    收货任务服务（PO 收货 / ORDER 退货）：

    commit 强规则（与业务一致）：
    - 对 has_shelf_life = true 的商品：
        * 必须 batch_code
        * 必须 production_date
        * expiry_date 可缺省：
            - 若 item 配置 shelf_life_value/unit：允许由 production_date 推算
            - 否则必须提供 expiry_date
    - 对 has_shelf_life = false 的商品：
        * 不要求日期（production/expiry 可为空）
        * batch_code 为空则自动 NOEXP
    """

    def __init__(self, inbound_svc: Optional[InboundService] = None) -> None:
        self.inbound_svc = inbound_svc or InboundService()

    async def create_for_po(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        warehouse_id: Optional[int] = None,
        include_fully_received: bool = False,
    ) -> ReceiveTask:
        return await _create_for_po(
            session,
            po_id=po_id,
            warehouse_id=warehouse_id,
            include_fully_received=include_fully_received,
        )

    async def create_for_order(
        self,
        session: AsyncSession,
        *,
        order_id: int,
        warehouse_id: Optional[int],
        lines: Sequence[OrderReturnLineIn],
    ) -> ReceiveTask:
        return await _create_for_order(
            session,
            order_id=order_id,
            warehouse_id=warehouse_id,
            lines=lines,
        )

    async def get_with_lines(
        self,
        session: AsyncSession,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> ReceiveTask:
        return await _get_with_lines(session, task_id, for_update=for_update)

    async def record_scan(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> ReceiveTask:
        return await _record_scan(
            session,
            task_id=task_id,
            item_id=item_id,
            qty=qty,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    async def commit(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> ReceiveTask:
        return await _commit(
            session,
            inbound_svc=self.inbound_svc,
            task_id=task_id,
            trace_id=trace_id,
            occurred_at=occurred_at,
            utc=UTC,
        )
