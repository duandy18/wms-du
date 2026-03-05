# tests/services/test_ledger_writer.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from tests.utils.ensure_minimal import ensure_item, ensure_warehouse

UTC = timezone.utc


@pytest.mark.asyncio
async def test_ledger_conservation(session: AsyncSession):
    """
    入库链路最小契约：

    - 使用 InboundService.receive(v2 签名：warehouse_id + batch_code) 落一笔入库；
    - 要求 stock_ledger 中至少有一条台账记录挂在本次 ref 名下。

    不再依赖 location_id（v1 模型），仅以 (warehouse_id, item_id, batch_code) 为库存粒度。
    """
    wh, item, code = 1, 7631, "LGD-7631"

    # 准备最小仓库 + 商品（Phase M：items policy NOT NULL，必须走合法插入）
    await ensure_warehouse(session, id=int(wh), name="WH-1")
    await ensure_item(session, id=int(item), sku=f"SKU-{item}", name=f"ITEM-{item}")

    await session.commit()

    ref = f"IN-LGD-{int(datetime.now(UTC).timestamp())}"
    svc = InboundService()
    exp = date.today() + timedelta(days=365)

    # 使用 v2 入库接口：warehouse_id + batch_code + expiry_date
    async with session.begin():
        _ = await svc.receive(
            session=session,
            item_id=item,
            sku=None,
            qty=3,
            ref=ref,
            occurred_at=datetime.now(UTC),
            warehouse_id=wh,
            batch_code=code,
            expiry_date=exp,
        )

    # 断言：至少有一条台账记录写入（具体 reason 由实现定义，这里只看 ref）
    row = await session.execute(
        text("SELECT COUNT(*) FROM stock_ledger WHERE ref = :r"),
        {"r": ref},
    )
    assert int(row.scalar_one()) >= 1
