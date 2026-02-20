# app/api/routers/purchase_orders_endpoints_dev_demo.py
"""
Purchase Orders Endpoints - Dev Demo（DevConsole 数据生成，仅开发辅助）
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.purchase_order import PurchaseOrderWithLinesOut
from app.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    @router.post("/dev-demo", response_model=PurchaseOrderWithLinesOut)
    async def create_demo_purchase_order(
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        wh_row = ((await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1"))).mappings().first())
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
            qty_ordered = base_qty * idx

            is_odd = (idx % 2) == 1
            spec_text = f"{85 * idx}g*{12 if is_odd else 6}袋"
            category = "猫条" if is_odd else "双拼"

            lines.append(
                {
                    "line_no": idx,
                    "item_id": item_id,
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
                supplier_id=supplier_id,
                warehouse_id=warehouse_id,
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
