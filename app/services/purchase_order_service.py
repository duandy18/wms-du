# app/services/purchase_order_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.purchase_order import PurchaseOrderWithLinesOut
from app.schemas.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.services.purchase_order_presenter import build_po_with_lines_out
from app.services.purchase_order_queries import get_po_with_lines as _get_po_with_lines
from app.services.purchase_order_receive import receive_po_line as _receive_po_line
from app.services.purchase_order_receive_workbench import get_receive_workbench

UTC = timezone.utc


class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）

    ✅ 合同加严（关键）：
    - base（最小单位）为唯一事实口径：qty_ordered_base
    - qty_ordered 为采购单位展示/输入快照（方案 A），units_per_case 为换算因子（>=1）

    ✅ 执行口径（关键）：
    - PO 行不再持久化 qty_received；已收/剩余一律来自 Receipt(CONFIRMED) 聚合视图（workbench / presenter 统一）
    """

    def __init__(self) -> None:
        # Phase5：禁止通过 InboundService 旁路写库存。
        # PO 的 receive-line 只能写 Receipt(DRAFT) 事实，不写 stock_ledger/stocks。
        pass

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
    ) -> Optional[PurchaseOrderWithLinesOut]:
        po = await _get_po_with_lines(session, po_id, for_update=for_update)
        if po is None:
            return None

        # ✅ 强制 refresh 头部字段，确保 close API 回显与 DB 一致
        try:
            await session.refresh(
                po,
                attribute_names=[
                    "status",
                    "last_received_at",
                    "closed_at",
                    "close_reason",
                    "close_note",
                    "closed_by",
                    "canceled_at",
                    "canceled_reason",
                    "canceled_by",
                ],
            )
        except Exception:
            pass

        return await build_po_with_lines_out(session, po)

    async def receive_po_line(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        qty: int,
        occurred_at: Optional[datetime] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ):
        return await _receive_po_line(
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            qty=qty,
            occurred_at=occurred_at,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    async def receive_po_line_workbench(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        qty: int,
        occurred_at: Optional[datetime] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        barcode: Optional[str] = None,
    ) -> PurchaseOrderReceiveWorkbenchOut:
        # 1) 写入 Receipt(DRAFT) 事实（Phase5+：内部已禁止隐式创建 draft）
        await _receive_po_line(
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            qty=qty,
            occurred_at=occurred_at,
            production_date=production_date,
            expiry_date=expiry_date,
            barcode=barcode,
        )

        # 2) 直接返回 workbench（前端只渲染，不再拼装）
        return await get_receive_workbench(session, po_id=int(po_id))
