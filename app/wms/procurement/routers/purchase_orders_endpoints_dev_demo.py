# app/wms/procurement/routers/purchase_orders_endpoints_dev_demo.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.purchase_order import PurchaseOrderWithLinesOut
from app.services.purchase_order_service import PurchaseOrderService


async def _pick_item_uom_id_for_po_line(session: AsyncSession, *, item_id: int) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM item_uoms
                 WHERE item_id = :i
                   AND is_purchase_default = true
                 ORDER BY id ASC
                 LIMIT 1
                """
            ),
            {"i": int(item_id)},
        )
    ).scalar_one_or_none()
    if row is not None:
        return int(row)

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM item_uoms
                 WHERE item_id = :i
                   AND is_base = true
                 ORDER BY id ASC
                 LIMIT 1
                """
            ),
            {"i": int(item_id)},
        )
    ).scalar_one_or_none()
    if row is not None:
        return int(row)

    raise HTTPException(status_code=400, detail=f"dev-demo: item_uoms missing for item_id={int(item_id)}")


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    @router.post("/dev-demo", response_model=PurchaseOrderWithLinesOut)
    async def create_demo_purchase_order(
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        wh_row = ((await session.execute(text("SELECT id FROM warehouses ORDER BY id LIMIT 1"))).mappings().first())
        if not wh_row:
            raise HTTPException(status_code=400, detail="warehouses 表为空")

        supplier_row = (
            (await session.execute(text("SELECT id FROM suppliers ORDER BY id LIMIT 1"))).mappings().first()
        )
        if not supplier_row:
            raise HTTPException(status_code=400, detail="suppliers 表为空")

        supplier_id = int(supplier_row["id"])
        warehouse_id = int(wh_row["id"])

        item_rows = (
            (await session.execute(text("SELECT id FROM items WHERE supplier_id = :sid LIMIT 5"), {"sid": supplier_id}))
            .mappings()
            .all()
        )
        if not item_rows:
            raise HTTPException(status_code=400, detail="没有可用商品")

        lines = []
        for idx, row in enumerate(item_rows, start=1):
            item_id = int(row["id"])
            uom_id = await _pick_item_uom_id_for_po_line(session, item_id=item_id)

            lines.append(
                {
                    "line_no": idx,
                    "item_id": item_id,
                    "qty": 10 * idx,
                    "uom_id": int(uom_id),
                    "supply_price": 10 * idx,
                    "remark": f"DEMO 行 {idx}",
                }
            )

        po = await svc.create_po_v2(
            session,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            purchaser="DEMO",
            purchase_time=datetime.now(timezone.utc),
            remark="Demo",
            lines=lines,
        )

        await session.commit()
        return await svc.get_po_with_lines(session, po.id)
