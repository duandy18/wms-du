# tests/helpers/po_testkit.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PoLineWorld:
    warehouse_id: int
    supplier_id: int
    supplier_name: str
    purchaser: str
    po_id: int
    po_line_id: int
    receipt_draft_id: int


async def get_any_warehouse_id(session: AsyncSession) -> int:
    """
    复用 seed 的 warehouse，避免在测试里猜 warehouses 表必填字段。
    """
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    r = row.first()
    if r is None or r[0] is None:
        raise RuntimeError("tests require at least one warehouse seeded in test database.")
    return int(r[0])


async def get_any_supplier(session: AsyncSession) -> tuple[int, str]:
    """
    purchase_orders.supplier_id / supplier_name 都是 NOT NULL：
    - supplier_id 从 suppliers 表拿一条 seed
    - supplier_name 兜底成非空字符串
    """
    row = await session.execute(text("SELECT id, name FROM suppliers ORDER BY id ASC LIMIT 1"))
    r = row.first()
    if r is None or r[0] is None:
        raise RuntimeError("tests require at least one supplier seeded in test database.")
    supplier_id = int(r[0])
    supplier_name = (str(r[1]).strip() if r[1] is not None else "").strip() or "UNKNOWN SUPPLIER"
    return supplier_id, supplier_name


async def get_any_purchaser(session: AsyncSession) -> str:
    """
    purchase_orders.purchaser NOT NULL：
    - 优先复用现存 PO 的 purchaser（更贴合真实约束/格式）
    - 没有就兜底
    """
    row = await session.execute(
        text("SELECT purchaser FROM purchase_orders WHERE purchaser IS NOT NULL ORDER BY id ASC LIMIT 1")
    )
    r = row.first()
    if r is None or r[0] is None:
        return "UT-PURCHASER"
    s = str(r[0]).strip()
    return s or "UT-PURCHASER"


async def create_po_with_line(
    session: AsyncSession,
    *,
    item_id: int,
    qty_ordered_base: int = 10,
    uom_snapshot: str = "EA",
    warehouse_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    supplier_name: Optional[str] = None,
    purchaser: Optional[str] = None,
    item_name: str = "UT-item-name",
    item_sku: str = "UT-item-sku",
    base_uom: Optional[str] = "EA",
    spec_text: Optional[str] = None,
) -> PoLineWorld:
    """
    固化“最小合法 PO + 单行”的创建逻辑（严格按当前 schema）：

    purchase_orders 必填：
    - warehouse_id
    - supplier_id
    - supplier_name
    - purchaser
    - purchase_time
    - status
    - created_at/updated_at

    purchase_order_lines 必填：
    - po_id
    - line_no
    - item_id
    - qty_ordered_base（>0）
    - discount_amount（NOT NULL）
    - uom_snapshot（NOT NULL）

    说明：
    - 本 helper 不负责创建 item（避免猜 items 表约束）。item 由测试提供。
    - 本 helper 只创建 PO / PO Line。
    """
    if qty_ordered_base <= 0:
        raise ValueError("qty_ordered_base must be > 0 (ck_po_lines_qty_ordered_base_positive).")

    wid = int(warehouse_id) if warehouse_id is not None else await get_any_warehouse_id(session)

    if supplier_id is None or supplier_name is None:
        sid, sname = await get_any_supplier(session)
        supplier_id = sid if supplier_id is None else supplier_id
        supplier_name = sname if supplier_name is None else supplier_name

    purchaser_val = purchaser if purchaser is not None else await get_any_purchaser(session)
    supplier_name_val = (str(supplier_name).strip() if supplier_name is not None else "").strip() or "UNKNOWN SUPPLIER"
    purchaser_val = (str(purchaser_val).strip() if purchaser_val is not None else "").strip() or "UT-PURCHASER"

    now = datetime.now(tz=timezone.utc)

    po_row = await session.execute(
        text(
            """
            INSERT INTO purchase_orders (
                warehouse_id,
                supplier_id, supplier_name,
                purchaser,
                purchase_time,
                status,
                created_at, updated_at
            )
            VALUES (
                :wid,
                :sid, :sname,
                :purchaser,
                :pt,
                'CREATED',
                :now, :now
            )
            RETURNING id
            """
        ),
        {
            "wid": wid,
            "sid": int(supplier_id),
            "sname": supplier_name_val,
            "purchaser": purchaser_val,
            "pt": now,
            "now": now,
        },
    )
    po_id = int(po_row.scalar_one())

    ln_row = await session.execute(
        text(
            """
            INSERT INTO purchase_order_lines (
                po_id, line_no, item_id,
                item_name, item_sku,
                spec_text, base_uom,
                qty_ordered_base,
                discount_amount,
                uom_snapshot
            )
            VALUES (
                :po_id, 1, :item_id,
                :item_name, :item_sku,
                :spec_text, :base_uom,
                :qty_ordered_base,
                0,
                :uom_snapshot
            )
            RETURNING id
            """
        ),
        {
            "po_id": po_id,
            "item_id": int(item_id),
            "item_name": item_name,
            "item_sku": item_sku,
            "spec_text": spec_text,
            "base_uom": base_uom,
            "qty_ordered_base": int(qty_ordered_base),
            "uom_snapshot": str(uom_snapshot),
        },
    )
    po_line_id = int(ln_row.scalar_one())

    return PoLineWorld(
        warehouse_id=wid,
        supplier_id=int(supplier_id),
        supplier_name=supplier_name_val,
        purchaser=purchaser_val,
        po_id=po_id,
        po_line_id=po_line_id,
        receipt_draft_id=0,
    )


async def create_po_with_line_and_draft_receipt(
    session: AsyncSession,
    *,
    item_id: int,
    qty_ordered_base: int = 10,
    uom_snapshot: str = "EA",
) -> PoLineWorld:
    """
    一步到位：创建 PO + 单行 + inbound_receipts(DRAFT)
    （receive_po_line 的硬前置条件）。
    """
    world = await create_po_with_line(
        session,
        item_id=item_id,
        qty_ordered_base=qty_ordered_base,
        uom_snapshot=uom_snapshot,
    )

    now = datetime.now(tz=timezone.utc)
    r_row = await session.execute(
        text(
            """
            INSERT INTO inbound_receipts (
                warehouse_id,
                source_type, source_id,
                ref, status,
                occurred_at, created_at, updated_at
            )
            VALUES (
                :wid,
                'PO', :po_id,
                :ref, 'DRAFT',
                :now, :now, :now
            )
            RETURNING id
            """
        ),
        {
            "wid": int(world.warehouse_id),
            "po_id": int(world.po_id),
            "ref": f"UT-DRFT-PO-{int(world.po_id)}",
            "now": now,
        },
    )
    rid = int(r_row.scalar_one())

    return PoLineWorld(
        warehouse_id=world.warehouse_id,
        supplier_id=world.supplier_id,
        supplier_name=world.supplier_name,
        purchaser=world.purchaser,
        po_id=world.po_id,
        po_line_id=world.po_line_id,
        receipt_draft_id=rid,
    )
