# app/services/purchase_order_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.schemas.purchase_order import PurchaseOrderLineOut, PurchaseOrderWithLinesOut
from app.services.inbound_service import InboundService
from app.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.services.purchase_order_queries import get_po_with_lines as _get_po_with_lines
from app.services.purchase_order_receive import receive_po_line as _receive_po_line

UTC = timezone.utc


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (
        (await session.execute(select(Item).where(Item.id.in_(item_ids))))
        .scalars()
        .all()
    )
    return {int(it.id): it for it in rows}


async def _load_primary_barcodes(session: AsyncSession, item_ids: List[int]) -> Dict[int, str]:
    """
    主条码规则（与 snapshot_inventory.py 保持一致）：
    - 仅 active=true
    - is_primary 优先，否则最小 id（稳定且可解释）
    """
    if not item_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(ItemBarcode)
                .where(ItemBarcode.item_id.in_(item_ids), ItemBarcode.active.is_(True))
                .order_by(ItemBarcode.item_id.asc(), ItemBarcode.is_primary.desc(), ItemBarcode.id.asc())
            )
        )
        .scalars()
        .all()
    )

    m: Dict[int, str] = {}
    for bc in rows:
        iid = int(bc.item_id)
        if iid in m:
            continue
        m[iid] = bc.barcode
    return m


class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）

    - create_po_v2: 创建“头 + 多行”的采购单；
    - get_po_with_lines: 获取带行的采购单（头 + 行），并补齐商品主数据字段；
    - receive_po_line: 针对某一行执行收货，并更新头表状态。
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
    ) -> Optional[PurchaseOrderWithLinesOut]:
        po = await _get_po_with_lines(session, po_id, for_update=for_update)
        if po is None:
            return None

        item_ids = sorted({int(ln.item_id) for ln in (po.lines or []) if ln.item_id})
        items_map = await _load_items_map(session, item_ids)
        barcode_map = await _load_primary_barcodes(session, item_ids)

        out_lines: List[PurchaseOrderLineOut] = []
        for ln in (po.lines or []):
            line_out = PurchaseOrderLineOut.model_validate(ln)

            # 兼容：PO 行历史 category -> biz_category（避免与 Item.category=品类冲突）
            line_out.biz_category = getattr(ln, "category", None)

            it = items_map.get(int(ln.item_id))
            if it is not None:
                # Item 主数据字段（与 ItemsListTable 列合同对齐）
                line_out.sku = it.sku
                line_out.brand = it.brand
                line_out.category = it.category
                line_out.supplier_id = it.supplier_id
                line_out.supplier_name = it.supplier_name
                line_out.weight_kg = getattr(it, "weight_kg", None)
                line_out.uom = it.uom

                line_out.has_shelf_life = it.has_shelf_life
                line_out.shelf_life_value = it.shelf_life_value
                line_out.shelf_life_unit = it.shelf_life_unit
                line_out.enabled = it.enabled

            line_out.primary_barcode = barcode_map.get(int(ln.item_id))
            out_lines.append(line_out)

        return PurchaseOrderWithLinesOut(
            id=po.id,
            supplier=po.supplier,
            warehouse_id=po.warehouse_id,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier_name,
            total_amount=po.total_amount,
            purchaser=po.purchaser,
            purchase_time=po.purchase_time,
            remark=po.remark,
            status=po.status,
            created_at=po.created_at,
            updated_at=po.updated_at,
            last_received_at=po.last_received_at,
            closed_at=po.closed_at,
            lines=out_lines,
        )

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
