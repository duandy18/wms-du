# app/procurement/repos/purchase_order_create_repo.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line import PurchaseOrderLine
from app.procurement.repos.purchase_order_line_completion_repo import (
    upsert_completion_rows_for_po,
)


async def reserve_purchase_order_id(session: AsyncSession) -> int:
    """
    预留 purchase_orders.id，便于 service 层用同一个 id 生成 po_no=PO-{id}。
    """
    row = await session.execute(text("SELECT nextval('purchase_orders_id_seq')"))
    return int(row.scalar_one())


async def require_item_uom_ratio_to_base(
    session: AsyncSession,
    *,
    item_id: int,
    uom_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT ratio_to_base
            FROM item_uoms
            WHERE id = :uom_id AND item_id = :item_id
            """
        ),
        {"uom_id": int(uom_id), "item_id": int(item_id)},
    )
    r = row.mappings().first()
    if r is None:
        raise ValueError(
            f"uom_id 不存在或不属于该商品：item_id={int(item_id)} uom_id={int(uom_id)}"
        )

    ratio = int(r.get("ratio_to_base") or 0)
    if ratio <= 0:
        raise ValueError("item_uoms.ratio_to_base 必须 >= 1")

    return ratio


async def pick_default_purchase_uom(
    session: AsyncSession,
    *,
    item_id: int,
) -> tuple[int, int]:
    """
    选择商品默认采购单位：
    1) is_purchase_default = true
    2) is_base = true
    3) 最小 id
    返回：(uom_id, ratio_to_base)
    """
    r1 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i AND is_purchase_default = true
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m1 = r1.mappings().first()
    if m1 is not None:
        return int(m1["id"]), int(m1["ratio_to_base"])

    r2 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i AND is_base = true
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m2 = r2.mappings().first()
    if m2 is not None:
        return int(m2["id"]), int(m2["ratio_to_base"])

    r3 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m3 = r3.mappings().first()
    if m3 is not None:
        return int(m3["id"]), int(m3["ratio_to_base"])

    raise ValueError(f"商品缺少 item_uoms：item_id={int(item_id)}")


async def insert_purchase_order_head(
    session: AsyncSession,
    *,
    po_id: int,
    po_no: str,
    supplier_id: int,
    supplier_name: str,
    warehouse_id: int,
    purchaser: str,
    purchase_time: datetime,
    total_amount: Decimal,
    remark: str | None,
) -> PurchaseOrder:
    po = PurchaseOrder(
        id=int(po_id),
        po_no=str(po_no),
        supplier_id=int(supplier_id),
        supplier_name=str(supplier_name),
        warehouse_id=int(warehouse_id),
        purchaser=str(purchaser),
        purchase_time=purchase_time,
        total_amount=total_amount,
        status="CREATED",
        remark=remark,
    )
    session.add(po)
    await session.flush()
    return po


async def insert_purchase_order_lines(
    session: AsyncSession,
    *,
    po_id: int,
    lines: Sequence[dict[str, Any]],
) -> None:
    for line in lines:
        session.add(PurchaseOrderLine(po_id=int(po_id), **dict(line)))
    await session.flush()

    # 同事务初始化采购行 completion 读表。
    await upsert_completion_rows_for_po(session, po_id=int(po_id))


__all__ = [
    "reserve_purchase_order_id",
    "require_item_uom_ratio_to_base",
    "pick_default_purchase_uom",
    "insert_purchase_order_head",
    "insert_purchase_order_lines",
]
