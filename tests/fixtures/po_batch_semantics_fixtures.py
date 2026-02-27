# tests/fixtures/po_batch_semantics_fixtures.py

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine


def _is_required_expiry_policy(expiry_policy: str) -> bool:
    return str(expiry_policy or "").strip().upper() == "REQUIRED"


# ---------------------------------------------------------
# 内部辅助：创建一个最小可运行 PO + 一行
# ---------------------------------------------------------

async def _create_po_with_one_line(
    session: AsyncSession,
    *,
    expiry_policy: str,
):
    # 1️⃣ 创建商品
    exp = str(expiry_policy or "").strip().upper() or "NONE"
    item = Item(
        name="UT-Item",
        sku="UT-SKU",
        # Phase M 真相源
        expiry_policy=exp,
        # 镜像字段：保持与 expiry_policy 一致（DB CHECK 会锁死等价）
        has_shelf_life=_is_required_expiry_policy(exp),
        base_uom="EA",
    )
    session.add(item)
    await session.flush()

    # 2️⃣ 创建采购单
    po = PurchaseOrder(
        warehouse_id=1,
        supplier_id=None,
        supplier_name=None,
        status="CREATED",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(po)
    await session.flush()

    # 3️⃣ 创建采购行
    line = PurchaseOrderLine(
        po_id=po.id,
        line_no=1,
        item_id=item.id,
        item_name=item.name,
        item_sku=item.sku,
        base_uom="EA",
        purchase_uom="EA",
        units_per_case=1,
        qty_ordered=10,      # purchase
        qty_ordered_base=10, # base
        unit_cost=None,
        line_amount=None,
    )
    session.add(line)
    await session.flush()

    # 重新加载 PO 及其 lines
    await session.refresh(po)
    await session.refresh(line)

    po.lines = [line]  # 简化测试环境访问

    return po


# ---------------------------------------------------------
# 1️⃣ 非效期商品（expiry_policy=NONE）
# ---------------------------------------------------------

@pytest.fixture
async def seeded_po_with_one_line_non_shelf_life(async_session: AsyncSession):
    po = await _create_po_with_one_line(
        async_session,
        expiry_policy="NONE",
    )
    await async_session.commit()
    return po


# ---------------------------------------------------------
# 2️⃣ 效期商品（expiry_policy=REQUIRED）
# ---------------------------------------------------------

@pytest.fixture
async def seeded_po_with_one_line_shelf_life(async_session: AsyncSession):
    po = await _create_po_with_one_line(
        async_session,
        expiry_policy="REQUIRED",
    )
    await async_session.commit()
    return po
