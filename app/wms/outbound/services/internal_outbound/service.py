# app/wms/outbound/services/internal_outbound/service.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.internal_outbound import InternalOutboundDoc
from app.wms.stock.services.stock_service import StockService

from app.wms.outbound.services.internal_outbound.ids import gen_doc_no as _gen_doc_no
from app.wms.outbound.services.internal_outbound.ids import gen_trace_id as _gen_trace_id
from app.wms.outbound.services.internal_outbound.lines import upsert_line as _upsert_line
from app.wms.outbound.services.internal_outbound.ops import cancel as _cancel
from app.wms.outbound.services.internal_outbound.ops import confirm as _confirm
from app.wms.outbound.services.internal_outbound.ops import create_doc as _create_doc
from app.wms.outbound.services.internal_outbound.query import get_with_lines as _get_with_lines


class InternalOutboundService:
    """
    内部出库服务（Internal Outbound）：
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    @staticmethod
    def _gen_doc_no(warehouse_id: int) -> str:
        return _gen_doc_no(warehouse_id)

    @staticmethod
    def _gen_trace_id(warehouse_id: int, doc_no: str) -> str:
        return _gen_trace_id(warehouse_id, doc_no)

    async def create_doc(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        doc_type: str,
        recipient_name: str,
        recipient_type: Optional[str] = None,
        recipient_note: Optional[str] = None,
        note: Optional[str] = None,
        created_by: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> InternalOutboundDoc:
        return await _create_doc(
            session,
            warehouse_id=warehouse_id,
            doc_type=doc_type,
            recipient_name=recipient_name,
            recipient_type=recipient_type,
            recipient_note=recipient_note,
            note=note,
            created_by=created_by,
            trace_id=trace_id,
        )

    async def get_with_lines(
        self,
        session: AsyncSession,
        doc_id: int,
        *,
        for_update: bool = False,
    ) -> InternalOutboundDoc:
        return await _get_with_lines(session, doc_id, for_update=for_update)

    async def upsert_line(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
        note: Optional[str] = None,
    ) -> InternalOutboundDoc:
        return await _upsert_line(
            session,
            doc_id=doc_id,
            item_id=item_id,
            qty=qty,
            batch_code=batch_code,
            note=note,
        )

    async def confirm(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        user_id: Optional[int] = None,
        occurred_at: Optional[datetime] = None,
    ) -> InternalOutboundDoc:
        # ✅ 以 internal_outbound_ops.confirm 的真实签名为准：
        # - 不传 stock_svc（不存在）
        # - 不传 occurred_at（不存在）
        _ = occurred_at
        return await _confirm(
            session,
            doc_id=doc_id,
            user_id=user_id,
        )

    async def cancel(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        user_id: Optional[int] = None,
    ) -> InternalOutboundDoc:
        return await _cancel(
            session,
            doc_id=doc_id,
            user_id=user_id,
        )
