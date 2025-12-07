import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_channel_inventory_case(session: AsyncSession):
    """
    构造一个简单但有代表性的多批次多锁量场景：

    - 仓库 WH=1 已由 tests/conftest 基线插入；
    - 使用测试专用 item_id=9001，避免与基线 stocks 冲突；
    - stocks:
        item 9001 @ WH1:   B-NEAR × 7, B-FAR × 3   => on_hand = 10
    - reservations (PDD, shop=RZ-CH-1, wh=1, ref='RZ-INV-001'):
        lines:
          item 9001: qty=4, consumed_qty=1 => open_lock = 3

    期望：
      - on_hand       = 10
      - reserved_open = 3
      - available     = 7
    """
    item_id = 9001
    wh_id = 1
    platform = "PDD"
    shop_id = "RZ-CH-1"
    ref = "RZ-INV-001"

    # 显式插入测试专用 item，保证外键安全
    await session.execute(
        text(
            """
            INSERT INTO items (id, sku, name)
            VALUES (:id, :sku, :name)
            ON CONFLICT (id) DO UPDATE
              SET sku = EXCLUDED.sku, name = EXCLUDED.name
            """
        ),
        {"id": item_id, "sku": f"SKU-{item_id}", "name": f"ITEM-{item_id}"},
    )

    # 两个批次
    await session.execute(
        text(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expire_at)
            VALUES
              (:item_id, :wh_id, 'B-NEAR', CURRENT_DATE + INTERVAL '10 day'),
              (:item_id, :wh_id, 'B-FAR',  CURRENT_DATE + INTERVAL '20 day')
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"item_id": item_id, "wh_id": wh_id},
    )

    # stocks 槽位：7 + 3 => on_hand = 10
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES
              (:item_id, :wh_id, 'B-NEAR', 7),
              (:item_id, :wh_id, 'B-FAR',  3)
            ON CONFLICT (item_id, warehouse_id, batch_code)
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"item_id": item_id, "wh_id": wh_id},
    )

    # reservation 头：open
    row = await session.execute(
        text(
            """
            INSERT INTO reservations (
                platform, shop_id, warehouse_id, ref,
                status, created_at, updated_at, expire_at
            )
            VALUES (
                :platform, :shop_id, :wh_id, :ref,
                'open', now(), now(), now() + INTERVAL '1 day'
            )
            RETURNING id
            """
        ),
        {"platform": platform, "shop_id": shop_id, "wh_id": wh_id, "ref": ref},
    )
    rid = int(row.scalar_one())

    # reservation line: qty=4, consumed_qty=1 => open_lock = 3
    await session.execute(
        text(
            """
            INSERT INTO reservation_lines (
                reservation_id,
                ref_line,
                item_id,
                qty,
                consumed_qty,
                created_at,
                updated_at
            )
            VALUES (
                :rid,
                1,
                :item_id,
                4,
                1,
                now(),
                now()
            )
            """
        ),
        {"rid": rid, "item_id": item_id},
    )

    await session.commit()
    return {
        "platform": platform,
        "shop_id": shop_id,
        "warehouse_id": wh_id,
        "item_id": item_id,
        "expected": {"on_hand": 10, "reserved_open": 3, "available": 7},
    }


async def test_channel_inventory_single(client, session: AsyncSession):
    """
    /channel-inventory/{platform}/{shop_id}/{warehouse_id}/{item_id}

    验证：
      - on_hand 等于 stocks.sum(qty)
      - reserved_open 等于 open reservations 的未消费数量
      - available = max(on_hand - reserved_open, 0)
      - batches 明细数量与 stocks 对应
    """
    seed = await _seed_channel_inventory_case(session)
    platform = seed["platform"]
    shop_id = seed["shop_id"]
    wh_id = seed["warehouse_id"]
    item_id = seed["item_id"]
    expected = seed["expected"]

    url = f"/channel-inventory/{platform}/{shop_id}/{wh_id}/{item_id}"
    resp = await client.get(url)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["platform"] == platform
    assert data["shop_id"] == shop_id
    assert data["warehouse_id"] == wh_id
    assert data["item_id"] == item_id

    assert data["on_hand"] == expected["on_hand"]
    assert data["reserved_open"] == expected["reserved_open"]
    assert data["available"] == expected["available"]

    # 批次明细也应该齐全（7 + 3）
    batches = data["batches"]
    assert isinstance(batches, list)
    assert {b["batch_code"] for b in batches} == {"B-NEAR", "B-FAR"}
    qty_by_batch = {b["batch_code"]: b["qty"] for b in batches}
    assert qty_by_batch["B-NEAR"] == 7
    assert qty_by_batch["B-FAR"] == 3
