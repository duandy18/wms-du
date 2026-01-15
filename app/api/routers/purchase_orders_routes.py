# app/api/routers/purchase_orders_routes.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order import (
    PurchaseOrderCreateV2,
    PurchaseOrderListItemOut,
    PurchaseOrderReceiveLineIn,
    PurchaseOrderWithLinesOut,
)
from app.schemas.purchase_order_receipts import PurchaseOrderReceiptEventOut
from app.services.purchase_order_receipts import list_po_receipt_events
from app.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    @router.post("/", response_model=PurchaseOrderWithLinesOut)
    async def create_purchase_order(
        payload: PurchaseOrderCreateV2,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        try:
            po = await svc.create_po_v2(
                session,
                supplier=payload.supplier,
                warehouse_id=payload.warehouse_id,
                supplier_id=payload.supplier_id,
                supplier_name=payload.supplier_name,
                purchaser=payload.purchaser,
                purchase_time=payload.purchase_time,
                remark=payload.remark,
                lines=[line.model_dump() for line in payload.lines],
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e)) from e

        po_out = await svc.get_po_with_lines(session, po.id)
        if po_out is None:
            raise HTTPException(status_code=500, detail="Failed to load created PurchaseOrder with lines")
        return po_out

    @router.get("/{po_id}", response_model=PurchaseOrderWithLinesOut)
    async def get_purchase_order(
        po_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        po_out = await svc.get_po_with_lines(session, po_id)
        if po_out is None:
            raise HTTPException(status_code=404, detail="PurchaseOrder not found")
        return po_out

    # ✅ 采购单历史收货事实（读台账）
    @router.get("/{po_id}/receipts", response_model=List[PurchaseOrderReceiptEventOut])
    async def get_purchase_order_receipts(
        po_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> List[PurchaseOrderReceiptEventOut]:
        try:
            return await list_po_receipt_events(session, po_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{po_id}/receive-line", response_model=PurchaseOrderWithLinesOut)
    async def receive_purchase_order_line(
        po_id: int,
        payload: PurchaseOrderReceiveLineIn,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        if payload.line_id is None and payload.line_no is None:
            raise HTTPException(status_code=400, detail="line_id 和 line_no 不能同时为空")

        try:
            po = await svc.receive_po_line(
                session,
                po_id=po_id,
                line_id=payload.line_id,
                line_no=payload.line_no,
                qty=payload.qty,
                production_date=getattr(payload, "production_date", None),
                expiry_date=getattr(payload, "expiry_date", None),
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e)) from e

        po_out = await svc.get_po_with_lines(session, po.id)
        if po_out is None:
            raise HTTPException(status_code=404, detail="PurchaseOrder not found after receive")
        return po_out

    # ✅ 列表态：返回 PurchaseOrderListItemOut（轻量，不含 qty_remaining）
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

        if supplier:
            stmt = stmt.where(PurchaseOrder.supplier.ilike(f"%{supplier.strip()}%"))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

        res = await session.execute(stmt)
        rows = list(res.scalars())

        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

        return [PurchaseOrderListItemOut.model_validate(po) for po in rows]

    @router.post("/dev-demo", response_model=PurchaseOrderWithLinesOut)
    async def create_demo_purchase_order(
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        wh_row = (
            (await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1")))
            .mappings()
            .first()
        )
        if not wh_row:
            raise HTTPException(status_code=400, detail="warehouses 表为空，请先创建仓库。")
        warehouse_id = int(wh_row["id"])

        # ✅ Phase 2 合同：必须绑定供应商（优先 active=true）
        supplier_row = (
            (await session.execute(text("SELECT id, name FROM suppliers WHERE active IS TRUE ORDER BY id LIMIT 1")))
            .mappings()
            .first()
        )
        if not supplier_row:
            supplier_row = (
                (await session.execute(text("SELECT id, name FROM suppliers ORDER BY id LIMIT 1")))
                .mappings()
                .first()
            )
        if not supplier_row:
            raise HTTPException(status_code=400, detail="suppliers 表为空，请先创建供应商。")

        supplier_id = int(supplier_row["id"])
        supplier_name = str(supplier_row.get("name") or f"SUPPLIER-{supplier_id}")

        # ✅ 关键修复：demo item 必须属于该 supplier_id，否则会触发“供应商->商品”硬闸
        item_rows = (
            (await session.execute(
                text("SELECT id, name FROM items WHERE supplier_id = :sid ORDER BY id LIMIT 5"),
                {"sid": supplier_id},
            ))
            .mappings()
            .all()
        )
        if not item_rows:
            raise HTTPException(
                status_code=400,
                detail=f"items 表中没有 supplier_id={supplier_id} 的商品，请先为该供应商创建商品。",
            )

        lines: list[dict] = []
        base_qty = 10
        for idx, row in enumerate(item_rows, start=1):
            item_id = int(row["id"])
            item_name = row.get("name") or f"ITEM-{item_id}"
            qty_ordered = base_qty * idx

            is_odd = (idx % 2) == 1
            spec_text = f"{85 * idx}g*{12 if is_odd else 6}袋"
            category = "猫条" if is_odd else "双拼"

            lines.append(
                {
                    "line_no": idx,
                    "item_id": item_id,
                    "item_name": item_name,
                    "qty_ordered": qty_ordered,
                    "category": category,
                    "spec_text": spec_text,
                    "base_uom": "袋",
                    "purchase_uom": "件",
                    "supply_price": 10 * idx,
                    "units_per_case": 1,
                    "remark": f"DEMO 行 {idx}",
                }
            )

        now = datetime.utcnow()
        try:
            po = await svc.create_po_v2(
                session,
                supplier=supplier_name,
                warehouse_id=warehouse_id,
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                purchaser="DEMO-PURCHASER",
                purchase_time=now,
                remark="Demo 采购单（DevConsole）",
                lines=lines,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e)) from e

        po_out = await svc.get_po_with_lines(session, po.id)
        if po_out is None:
            raise HTTPException(status_code=500, detail="Failed to load demo PurchaseOrder with lines")
        return po_out
