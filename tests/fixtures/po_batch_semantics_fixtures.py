# tests/fixtures/po_batch_semantics_fixtures.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.items.models.item import Item
from app.pms.items.models.item_uom import ItemUOM
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine


def _is_required_expiry_policy(expiry_policy: str) -> bool:
    return str(expiry_policy or "").strip().upper() == "REQUIRED"


async def _get_any_supplier(session: AsyncSession) -> tuple[int, str]:
    row = await session.execute(text("SELECT id, name FROM suppliers ORDER BY id ASC LIMIT 1"))
    r = row.first()
    if r is None or r[0] is None:
        raise RuntimeError("tests require at least one supplier seeded in test database.")
    sid = int(r[0])
    sname = (str(r[1]).strip() if r[1] is not None else "").strip() or "UNKNOWN SUPPLIER"
    return sid, sname


async def _get_any_warehouse_id(session: AsyncSession) -> int:
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    r = row.first()
    if r is None or r[0] is None:
        raise RuntimeError("tests require at least one warehouse seeded in test database.")
    return int(r[0])


# ---------------------------------------------------------
# 内部辅助：创建一个最小可运行 PO + 一行（按 Phase M-5 新合同）
# ---------------------------------------------------------
async def _create_po_with_one_line(
    session: AsyncSession,
    *,
    expiry_policy: str,
):
    exp = str(expiry_policy or "").strip().upper() or "NONE"

    # 1️⃣ 复用 seed 的 supplier/warehouse（不猜表必填字段）
    wid = await _get_any_warehouse_id(session)
    sid, sname = await _get_any_supplier(session)

    # 2️⃣ 创建商品（按当前 items schema）
    # 注意：sku 唯一；fixture 用时间戳避免冲突
    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    item = Item(
        name="UT-Item",
        sku=f"UT-SKU-{ts}",
        uom="EA",
        enabled=True,
        supplier_id=sid,
        lot_source_policy="SUPPLIER_ONLY",
        expiry_policy=exp,
        derivation_allowed=True,
        uom_governance_enabled=True,
        shelf_life_value=(30 if _is_required_expiry_policy(exp) else None),
        shelf_life_unit=("DAY" if _is_required_expiry_policy(exp) else None),
    )
    session.add(item)
    await session.flush()

    # 3️⃣ 创建 base item_uom（ratio=1）
    uom = ItemUOM(
        item_id=int(item.id),
        uom="EA",
        ratio_to_base=1,
        display_name=None,
        is_base=True,
        is_purchase_default=True,
        is_inbound_default=True,
        is_outbound_default=True,
    )
    session.add(uom)
    await session.flush()

    # 4️⃣ 创建采购单（按 purchase_orders NOT NULL）
    now = datetime.now(tz=timezone.utc)
    po = PurchaseOrder(
        warehouse_id=wid,
        supplier_id=sid,
        supplier_name=sname,
        purchaser="UT-PURCHASER",
        purchase_time=now,
        status="CREATED",
        total_amount=None,
        remark=None,
        created_at=now,
        updated_at=now,
    )
    session.add(po)
    await session.flush()

    # 5️⃣ 创建采购行（按 Phase M-5 新合同）
    qty_base = 10
    line = PurchaseOrderLine(
        po_id=int(po.id),
        line_no=1,
        item_id=int(item.id),
        item_name=item.name,
        item_sku=item.sku,
        spec_text=None,
        purchase_uom_id_snapshot=int(uom.id),
        purchase_ratio_to_base_snapshot=1,
        qty_ordered_input=qty_base,
        qty_ordered_base=qty_base,
        supply_price=None,
        discount_amount=0,
        discount_note=None,
        remark=None,
    )
    session.add(line)
    await session.flush()

    await session.refresh(po)
    await session.refresh(line)
    po.lines = [line]
    return po


@pytest.fixture
async def seeded_po_with_one_line_non_shelf_life(async_session: AsyncSession):
    po = await _create_po_with_one_line(async_session, expiry_policy="NONE")
    await async_session.commit()
    return po


@pytest.fixture
async def seeded_po_with_one_line_shelf_life(async_session: AsyncSession):
    po = await _create_po_with_one_line(async_session, expiry_policy="REQUIRED")
    await async_session.commit()
    return po
