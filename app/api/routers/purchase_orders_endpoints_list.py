# app/api/routers/purchase_orders_endpoints_list.py
"""
Purchase Orders Endpoints - List（列表读模型）
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.models.warehouse import Warehouse
from app.schemas.purchase_order import PurchaseOrderLineListOut, PurchaseOrderListItemOut
from app.services.purchase_order_line_mapper import build_line_base_data
from app.services.purchase_order_service import PurchaseOrderService


async def _load_confirmed_received_base_map(
    session: AsyncSession, *, po_line_ids: list[int]
) -> dict[int, int]:
    """
    维度：po_line_id -> sum(qty_received)（仅 CONFIRMED receipts）
    """
    if not po_line_ids:
        return {}

    sql = text(
        """
        SELECT rl.po_line_id AS po_line_id,
               COALESCE(SUM(rl.qty_received), 0)::int AS qty
          FROM inbound_receipt_lines rl
          JOIN inbound_receipts r
            ON r.id = rl.receipt_id
         WHERE r.source_type = 'PO'
           AND r.status = 'CONFIRMED'
           AND rl.po_line_id = ANY(:ids)
         GROUP BY rl.po_line_id
        """
    )
    rows = (await session.execute(sql, {"ids": [int(x) for x in po_line_ids]})).mappings().all()
    out: dict[int, int] = {}
    for r in rows:
        pid = int(r.get("po_line_id") or 0)
        if pid > 0:
            out[pid] = int(r.get("qty") or 0)
    return out


def register(router: APIRouter, _svc: PurchaseOrderService) -> None:
    @router.get("/", response_model=List[PurchaseOrderListItemOut])
    async def list_purchase_orders(
        session: AsyncSession = Depends(get_session),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        supplier: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
    ) -> List[PurchaseOrderListItemOut]:
        stmt = (
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.lines))
            .order_by(PurchaseOrder.id.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
        )

        # ✅ 废除 supplier 自由文本：列表搜索走 supplier_name
        if supplier:
            stmt = stmt.where(PurchaseOrder.supplier_name.ilike(f"%{supplier.strip()}%"))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

        res = await session.execute(stmt)
        rows = list(res.scalars())

        # warehouses map
        wh_ids = sorted(
            {
                int(getattr(po, "warehouse_id"))
                for po in rows
                if getattr(po, "warehouse_id", None) is not None
            }
        )
        wh_map: dict[int, str] = {}
        if wh_ids:
            wh_rows = (
                await session.execute(
                    select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(wh_ids))
                )
            ).all()
            for wid, name in wh_rows:
                if wid is None:
                    continue
                wh_map[int(wid)] = str(name or "")

        # ✅ 收货事实聚合：po_line_id -> confirmed_received_base
        po_line_ids: list[int] = []
        for po in rows:
            for ln in po.lines or []:
                lid = getattr(ln, "id", None)
                if lid is not None:
                    try:
                        po_line_ids.append(int(lid))
                    except Exception:
                        pass
        received_map = await _load_confirmed_received_base_map(session, po_line_ids=po_line_ids)

        out: List[PurchaseOrderListItemOut] = []
        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

            line_out: List[PurchaseOrderLineListOut] = []
            for ln in po.lines or []:
                ln_id = int(getattr(ln, "id"))
                received_base = int(received_map.get(ln_id, 0) or 0)

                # ✅ 统一来源：行本体 + 执行口径（base）+ 快照解释器 由 mapper 负责
                data = build_line_base_data(ln=ln, received_base=received_base)

                line_out.append(
                    PurchaseOrderLineListOut(
                        id=int(data["id"]),
                        po_id=int(data["po_id"]),
                        line_no=int(data["line_no"]),
                        item_id=int(data["item_id"]),
                        # ✅ 快照解释器（第一公民）
                        uom_snapshot=data.get("uom_snapshot"),
                        case_ratio_snapshot=data.get("case_ratio_snapshot"),
                        case_uom_snapshot=data.get("case_uom_snapshot"),
                        qty_ordered_case_input=data.get("qty_ordered_case_input"),
                        # ✅ 事实/执行口径（base）
                        qty_ordered_base=int(data["qty_ordered_base"]),
                        qty_received_base=int(data["qty_received_base"]),
                        qty_remaining_base=int(data["qty_remaining_base"]),
                        # 其他字段
                        base_uom=data.get("base_uom"),
                        supply_price=data.get("supply_price"),
                        discount_amount=data.get("discount_amount") or 0,
                        discount_note=data.get("discount_note"),
                        remark=data.get("remark"),
                        created_at=data["created_at"],
                        updated_at=data["updated_at"],
                    )
                )

            wid = int(getattr(po, "warehouse_id"))
            out.append(
                PurchaseOrderListItemOut(
                    id=int(getattr(po, "id")),
                    warehouse_id=wid,
                    warehouse_name=wh_map.get(wid) or None,
                    supplier_id=int(getattr(po, "supplier_id")),
                    supplier_name=str(getattr(po, "supplier_name") or ""),
                    total_amount=getattr(po, "total_amount", None),
                    purchaser=str(getattr(po, "purchaser") or ""),
                    purchase_time=getattr(po, "purchase_time"),
                    remark=getattr(po, "remark", None),
                    status=str(getattr(po, "status") or ""),
                    created_at=getattr(po, "created_at"),
                    updated_at=getattr(po, "updated_at"),
                    last_received_at=getattr(po, "last_received_at", None),
                    closed_at=getattr(po, "closed_at", None),
                    close_reason=getattr(po, "close_reason", None),
                    close_note=getattr(po, "close_note", None),
                    closed_by=getattr(po, "closed_by", None),
                    canceled_at=getattr(po, "canceled_at", None),
                    canceled_reason=getattr(po, "canceled_reason", None),
                    canceled_by=getattr(po, "canceled_by", None),
                    lines=line_out,
                )
            )

        return out
