# app/services/purchase_order_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.services.purchase_order_queries import get_po_with_lines as _get_po_with_lines
from app.services.purchase_order_receive import receive_po_line as _receive_po_line

UTC = timezone.utc


class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）

    - create_po_v2: 创建“头 + 多行”的采购单；
    - get_po_with_lines: 获取带行的采购单（头 + 行）；
    - receive_po_line: 针对某一行执行收货，并更新头表状态。

    金额约定（非常重要）：

    - qty_ordered：订购“件数”（采购单位，如 件/箱）
    - units_per_case：每件包含的最小单位数量（如每箱 8 袋）
    - supply_price：采购价格，按“最小单位”计价（单袋价格）
    - 行金额 line_amount = qty_ordered × units_per_case × supply_price
      若 units_per_case 为空，则退化为 qty_ordered × supply_price
    - total_amount = 所有行 line_amount 的和
    """

    def __init__(self, inbound_svc: Optional[InboundService] = None) -> None:
        self.inbound_svc = inbound_svc or InboundService()

    async def create_po_v2(
        self,
        session: AsyncSession,
        *,
        supplier: str,
        warehouse_id: int,
        supplier_id: Optional[int] = None,
        supplier_name: Optional[str] = None,
        purchaser: str,
        purchase_time: datetime,
        remark: Optional[str] = None,
        lines: List[Dict[str, Any]],
    ):
        return await _create_po_v2(
            session,
            supplier=supplier,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            purchaser=purchaser,
            purchase_time=purchase_time,
            remark=remark,
            lines=lines,
        )

    async def get_po_with_lines(
        self,
        session: AsyncSession,
        po_id: int,
        *,
        for_update: bool = False,
    ):
        return await _get_po_with_lines(session, po_id, for_update=for_update)

    async def receive_po_line(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        qty: int,
        occurred_at: Optional[datetime] = None,
    ):
        return await _receive_po_line(
            self.inbound_svc,
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            qty=qty,
            occurred_at=occurred_at,
        )
