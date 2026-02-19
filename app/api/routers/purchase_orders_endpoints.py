# app/api/routers/purchase_orders_endpoints.py
"""
Purchase Orders Endpoints（内部模块，封板）

硬规则：
- 本文件只提供 register(router, svc)，不创建/导出 APIRouter 实例。
- 禁止在 app/main.py 直接 include 本文件。
- /purchase-orders 的唯一 router 入口是：app/api/routers/purchase_orders.py

目的：
- 防止重复挂载与路径覆盖
- 防止 response_model 契约漂移（例如 base 字段缺失导致前端“无可收货行”）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.models.warehouse import Warehouse
from app.schemas.purchase_order import (
    PurchaseOrderCreateV2,
    PurchaseOrderLineListOut,
    PurchaseOrderListItemOut,
    PurchaseOrderReceiveLineIn,
    PurchaseOrderWithLinesOut,
)
from app.schemas.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.schemas.purchase_order_receipts import PurchaseOrderReceiptEventOut
from app.services.purchase_order_receipts import list_po_receipt_events
from app.services.purchase_order_service import PurchaseOrderService
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl


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

    # ✅ Phase5+：收货录入后直接返回 workbench（前端不再拼装 PO + Receipt + Explain）
    @router.post("/{po_id}/receive-line", response_model=PurchaseOrderReceiveWorkbenchOut)
    async def receive_purchase_order_line(
        po_id: int,
        payload: PurchaseOrderReceiveLineIn,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderReceiveWorkbenchOut:
        if payload.line_id is None and payload.line_no is None:
            raise HTTPException(status_code=400, detail="line_id 和 line_no 不能同时为空")

        try:
            out = await svc.receive_po_line_workbench(
                session,
                po_id=po_id,
                line_id=payload.line_id,
                line_no=payload.line_no,
                qty=payload.qty,
                production_date=getattr(payload, "production_date", None),
                expiry_date=getattr(payload, "expiry_date", None),
                barcode=getattr(payload, "barcode", None),
            )
            await session.commit()
            return out
        except ValueError as e:
            await session.rollback()
            msg = str(e)

            # Phase5+ 收敛：未显式开始收货 → 409（前端据此引导先 POST /receipts/draft）
            if "请先开始收货" in msg or "未找到 PO 的 DRAFT 收货单" in msg:
                raise HTTPException(status_code=409, detail=msg) from e

            raise HTTPException(status_code=400, detail=msg) from e

    # ✅ 列表态：返回 PurchaseOrderListItemOut（轻量）
    # ✅ 合同加严：列表态行必须显性返回 qty_ordered_base / qty_received_base（base 真相），避免前端自行推导。
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

        # ✅ 批量加载仓库名称（展示字段，不写入 purchase_orders 表）
        wh_ids = sorted({int(getattr(po, "warehouse_id")) for po in rows if getattr(po, "warehouse_id", None) is not None})
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

        out: List[PurchaseOrderListItemOut] = []
        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

            line_out: List[PurchaseOrderLineListOut] = []
            for ln in (po.lines or []):
                ordered_base = int(_ordered_base_impl(ln) or 0)
                received_base = int(_received_base_impl(ln) or 0)

                line_out.append(
                    PurchaseOrderLineListOut(
                        id=int(getattr(ln, "id")),
                        po_id=int(getattr(ln, "po_id")),
                        line_no=int(getattr(ln, "line_no")),
                        item_id=int(getattr(ln, "item_id")),
                        qty_ordered=int(getattr(ln, "qty_ordered") or 0),
                        qty_ordered_base=ordered_base,
                        qty_received_base=received_base,
                        status=str(getattr(ln, "status") or ""),
                        units_per_case=getattr(ln, "units_per_case", None),
                        base_uom=getattr(ln, "base_uom", None),
                        purchase_uom=getattr(ln, "purchase_uom", None),
                        created_at=getattr(ln, "created_at"),
                        updated_at=getattr(ln, "updated_at"),
                    )
                )

            wid = int(getattr(po, "warehouse_id"))
            out.append(
                PurchaseOrderListItemOut(
                    id=int(getattr(po, "id")),
                    supplier=str(getattr(po, "supplier") or ""),
                    warehouse_id=wid,
                    warehouse_name=wh_map.get(wid) or None,
                    supplier_id=getattr(po, "supplier_id", None),
                    supplier_name=getattr(po, "supplier_name", None),
                    total_amount=getattr(po, "total_amount", None),
                    purchaser=str(getattr(po, "purchaser") or ""),
                    purchase_time=getattr(po, "purchase_time"),
                    remark=getattr(po, "remark", None),
                    status=str(getattr(po, "status") or ""),
                    created_at=getattr(po, "created_at"),
                    updated_at=getattr(po, "updated_at"),
                    last_received_at=getattr(po, "last_received_at", None),
                    closed_at=getattr(po, "closed_at", None),
                    lines=line_out,
                )
            )

        return out

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

        item_rows = (
            (
                await session.execute(
                    text("SELECT id, name FROM items WHERE supplier_id = :sid ORDER BY id LIMIT 5"),
                    {"sid": supplier_id},
                )
            )
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

        now = datetime.now(timezone.utc)
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
            raise HTTPException(status_code=500, detail="Failed to load deo PurchaseOrder with lines")
        return po_out
