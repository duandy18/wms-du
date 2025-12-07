# tests/services/test_outbound_sandbox_phase4_routing.py
import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_warehouses(session, n: int) -> list[int]:
    rows = await session.execute(text("SELECT id FROM warehouses ORDER BY id"))
    ids = [int(r[0]) for r in rows.fetchall()]

    needed = n - len(ids)
    if needed <= 0:
        return ids[:n]

    cols_rows = await session.execute(
        text(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'warehouses'
               AND is_nullable  = 'NO'
               AND column_default IS NULL
               AND column_name <> 'id'
            """
        )
    )
    col_info = [(str(r[0]), str(r[1])) for r in cols_rows.fetchall()]

    if not col_info:
        for _ in range(needed):
            row = await session.execute(text("INSERT INTO warehouses DEFAULT VALUES RETURNING id"))
            ids.append(int(row.scalar()))
        return ids[:n]

    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    for _ in range(needed):
        params = {}
        for col, dtype in col_info:
            dt = dtype.lower()
            if "char" in dt or "text" in dt:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:8]}"
            elif "int" in dt:
                params[col] = 0
            elif "bool" in dt:
                params[col] = False
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(UTC)
            elif dt == "date":
                params[col] = datetime.now(UTC).date()
            else:
                params[col] = f"WH-{col}-{uuid.uuid4().hex[:4]}"
        row = await session.execute(text(sql), params)
        ids.append(int(row.scalar()))
    return ids[:n]


async def _ensure_store(session, platform: str, shop_id: str, name: str, route_mode: str) -> int:
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": platform, "s": shop_id},
    )
    sid = row.scalar()
    if sid is None:
        # 简化版插入：假设只有 name 是 NOT NULL
        await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name, route_mode)
                VALUES (:p, :s, :n, :m)
                ON CONFLICT (platform, shop_id) DO NOTHING
                """
            ),
            {"p": platform, "s": shop_id, "n": name, "m": route_mode},
        )
        row2 = await session.execute(
            text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
            {"p": platform, "s": shop_id},
        )
        sid = row2.scalar()
    else:
        await session.execute(
            text("UPDATE stores SET route_mode=:m WHERE id=:sid"),
            {"m": route_mode, "sid": sid},
        )
    return int(sid)


async def _bind_store_wh(session, store_id: int, wh_top: int, wh_backup: int):
    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id=:sid"),
        {"sid": store_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, TRUE, 10)
            """
        ),
        {"sid": store_id, "wid": wh_top},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, FALSE, 20)
            """
        ),
        {"sid": store_id, "wid": wh_backup},
    )


@pytest.mark.asyncio
async def test_outbound_sandbox_phase4_routing(db_session_like_pg, monkeypatch):
    """
    小型沙盘：2 仓 + 3 店 + 多订单，检查：

    - FALLBACK 店在主仓不足时会 fallback 到备仓；
    - STRICT_TOP 店在主仓不足时不会 fallback；
    - 常规店（主仓足够）永远在主仓发。
    """
    session = db_session_like_pg
    platform = "PDD"

    wh_a, wh_b = await _ensure_warehouses(session, 2)

    # 三家店：S1 普通 FALLBACK；S2 严格 STRICT_TOP；S3 FALLBACK 但主仓永远足够
    s1 = await _ensure_store(session, platform, "S1-FB", "Shop FB", route_mode="FALLBACK")
    s2 = await _ensure_store(session, platform, "S2-ST", "Shop ST", route_mode="STRICT_TOP")
    s3 = await _ensure_store(session, platform, "S3-FBOK", "Shop FB-OK", route_mode="FALLBACK")

    await _bind_store_wh(session, s1, wh_a, wh_b)
    await _bind_store_wh(session, s2, wh_a, wh_b)
    await _bind_store_wh(session, s3, wh_a, wh_b)

    # 可用库存策略：
    # - S1 对 wh_a 不足，对 wh_b 足够 → 应 fallback 到 wh_b
    # - S2 同上 → STRICT_TOP 不应 fallback，wh_id 为空/0
    # - S3 对 wh_a 足够 → 永远 wh_a
    stock_map = {
        (wh_a, 1, "S1-FB"): 2,
        (wh_b, 1, "S1-FB"): 10,
        (wh_a, 1, "S2-ST"): 2,
        (wh_b, 1, "S2-ST"): 10,
        (wh_a, 1, "S3-FBOK"): 10,
        (wh_b, 1, "S3-FBOK"): 0,
    }

    async def fake_get_available(self, session_, platform_, shop_id_, warehouse_id, item_id):
        key = (warehouse_id, item_id, shop_id_)
        return int(stock_map.get(key, 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

    async def _place(platform: str, shop_id: str, ext: str) -> int:
        res = await OrderService.ingest(
            session,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext,
            occurred_at=datetime.now(UTC),
            buyer_name=f"Buyer-{shop_id}",
            buyer_phone="000",
            order_amount=50,
            pay_amount=50,
            items=[
                {
                    "item_id": 1,
                    "sku_id": "SKU-1",
                    "title": f"ITEM-{shop_id}",
                    "qty": 5,
                    "price": 10,
                    "discount": 0,
                    "amount": 50,
                }
            ],
            address={"receiver_name": "X", "receiver_phone": "000"},
            extras={},
            trace_id=f"TRACE-SANDBOX-{shop_id}",
        )
        assert res["status"] == "OK"
        return int(res["id"])

    oid1 = await _place(platform, "S1-FB", "ORD-S1-001")
    oid2 = await _place(platform, "S2-ST", "ORD-S2-001")
    oid3 = await _place(platform, "S3-FBOK", "ORD-S3-001")

    def _get_wh(order_id: int) -> Optional[int]:
        return session.run_sync(
            lambda s: s.execute(
                text("SELECT warehouse_id FROM orders WHERE id=:id"),
                {"id": order_id},
            ).scalar()
        )

    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid1})
    wh1 = row.scalar()
    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid2})
    wh2 = row.scalar()
    row = await session.execute(text("SELECT warehouse_id FROM orders WHERE id=:id"), {"id": oid3})
    wh3 = row.scalar()

    # S1：FALLBACK，主仓不足，备仓足够 → 应 fallback 到 wh_b
    assert wh1 == wh_b

    # S2：STRICT_TOP，主仓不足，备仓也有货 → 不 fallback，保持空
    assert wh2 in (None, 0)

    # S3：FALLBACK，但主仓库存足够 → 应在 wh_a
    assert wh3 == wh_a
