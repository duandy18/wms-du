# tests/services/test_order_adapter_pdd.py
from datetime import datetime

import pytest
from sqlalchemy import text

from app.services.order_service import OrderService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_pdd_adapter_ingest_raw_writes_extras(session):
    payload = {
        "mall_id": "SHOP-001",
        "order_sn": "PDD-UT-1001",
        "created_at": datetime.utcnow().isoformat(),
        "receiver_name": "张三",
        "receiver_phone": "13800000000",
        "goods_amount": 199.0,
        "pay_amount": 188.0,
        "items": [
            {
                "sku_id": "SKU-PDD-1",
                "goods_name": "猫粮A",
                "quantity": 2,
                "goods_price": 99.5,
                "outer_sku_id": "OUT-1",
            },
        ],
        "seller_memo": "门店备注",
        "flags": ["urgent"],
        "id": "RAW-1001",
    }
    r = await OrderService.ingest_raw(session, platform="PDD", shop_id="SHOP-001", payload=payload)
    await session.commit()
    assert r["status"] in ("OK", "IDEMPOTENT")

    # 验证 extras 落在 orders
    rec = await session.execute(
        text(
            """
        SELECT (extras->>'remark') AS remark, (extras->>'flags') IS NOT NULL AS has_flags
        FROM orders WHERE platform='PDD' AND shop_id='SHOP-001' AND ext_order_no='PDD-UT-1001'
    """
        )
    )
    row = rec.first()
    assert row is not None
    assert row[0] == "门店备注"
    assert row[1] is True

    # 验证 extras 落在 order_items
    rec2 = await session.execute(
        text(
            """
        SELECT COUNT(*) FROM order_items
        WHERE sku_id='SKU-PDD-1' AND (extras->>'outer_sku_id')='OUT-1'
    """
        )
    )
    assert (rec2.scalar() or 0) >= 1
