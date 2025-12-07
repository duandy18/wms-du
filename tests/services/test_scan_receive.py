# tests/services/test_scan_receive.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService

UTC = timezone.utc


@pytest.mark.asyncio
async def test_scan_receive_commits_ledger(session: AsyncSession):
    """
    v2 入库服务测试（warehouse + item + batch 粒度）：

    - 不依赖 location_id，也不依赖 tests.utils 中的 helper。
    - 通过 InboundService.receive 使用 sku 自动建 item。
    - 校验 stocks 表中 (warehouse_id, item_id, batch_code) 的 qty 被正确更新。
    """

    warehouse_id = 1
    sku = "SKU-TEST-INBOUND-3001"
    batch_code = "RCV-3001"
    qty = 3
    expiry = date.today() + timedelta(days=365)
    ref = f"IN-{int(datetime.now(UTC).timestamp())}"

    svc = InboundService()

    # 不再显式 session.begin()，session fixture 已经管理事务
    res = await svc.receive(
        session=session,
        # 不提供 item_id，改用 sku，由 InboundService._ensure_item_id 自动建档
        item_id=None,
        sku=sku,
        qty=qty,
        ref=ref,
        occurred_at=datetime.now(UTC),
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        expiry_date=expiry,
    )

    # 返回值基本字段校验
    item_id = res["item_id"]
    assert item_id > 0
    assert res["warehouse_id"] == warehouse_id
    assert res["batch_code"] == batch_code
    assert res["qty"] == qty

    # 验证 stocks 表中该批次库存为 qty
    row = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code = :c
            """
        ),
        {"i": item_id, "w": warehouse_id, "c": batch_code},
    )
    db_qty = row.scalar_one()
    assert db_qty == qty
