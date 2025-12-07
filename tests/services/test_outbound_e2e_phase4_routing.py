# tests/services/test_outbound_e2e_phase4_routing.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService, ShipLine


async def _get_store_id_for_shop(session: AsyncSession, platform: str, shop_id: str) -> int:
    """
    获取或创建给定 platform/shop_id 的 store 记录，返回 store.id。
    测试环境是干净库，不再依赖预先 seed 的 store。
    """
    row = await session.execute(
        text(
            """
            SELECT id
              FROM stores
             WHERE platform = :p
               AND shop_id  = :s
             LIMIT 1
            """
        ),
        {"p": platform, "s": shop_id},
    )
    store_id = row.scalar()
    if store_id is None:
        row = await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name)
                VALUES (:p, :s, :name)
                RETURNING id
                """
            ),
            {"p": platform, "s": shop_id, "name": f"UT-STORE-{platform}-{shop_id}"},
        )
        store_id = row.scalar_one()
    return int(store_id)


async def _ensure_two_warehouses(session):
    """
    返回两个 warehouse_id 作为主 / 备。
    如果现有仓库数量不足 2 个，则动态插入测试仓。
    """
    rows = await session.execute(
        text(
            """
            SELECT id
              FROM warehouses
             ORDER BY id
            """
        )
    )
    ids = [int(r[0]) for r in rows.fetchall()]

    needed = 2 - len(ids)
    if needed <= 0:
        return ids[0], ids[1]

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
        return ids[0], ids[1]

    columns = ", ".join(c for c, _ in col_info)
    placeholders = ", ".join(f":{c}" for c, _ in col_info)
    sql = f"INSERT INTO warehouses ({columns}) VALUES ({placeholders}) RETURNING id"

    for _ in range(needed):
        params = {}
        for col, dtype in col_info:
            dt = dtype.lower()
            if "char" in dt or "text" in dt:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:8]}"
            elif "int" in dt:
                params[col] = 0
            elif "bool" in dt:
                params[col] = False
            elif "timestamp" in dt or "time" in dt:
                params[col] = datetime.now(timezone.utc)
            elif dt == "date":
                params[col] = datetime.now(timezone.utc).date()
            else:
                params[col] = f"TEST_{col}_{uuid.uuid4().hex[:4]}"
        row = await session.execute(text(sql), params)
        ids.append(int(row.scalar()))

    return ids[0], ids[1]


async def _bind_store_warehouses(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    top_warehouse_id: int,
    backup_warehouse_id: int,
):
    """
    清空该店铺旧的 store_warehouse 记录，并绑定主 / 备仓。
    """
    store_id = await _get_store_id_for_shop(session, platform, shop_id)

    await session.execute(
        text("DELETE FROM store_warehouse WHERE store_id = :sid"),
        {"sid": store_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, :top, :pr)
            """
        ),
        {"sid": store_id, "wid": top_warehouse_id, "top": True, "pr": 10},
    )

    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, :wid, :top, :pr)
            """
        ),
        {"sid": store_id, "wid": backup_warehouse_id, "top": False, "pr": 1},
    )


@pytest.mark.asyncio
async def test_ingest_reserve_ship_e2e_phase4(db_session_like_pg, monkeypatch):
    """
    Phase 4：ingest → reserve → ship 全链路 E2E（单平台单店）
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    # 准备主仓 / 备仓，并绑定到店铺
    top_wid, backup_wid = await _ensure_two_warehouses(session)
    await _bind_store_warehouses(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    # 为路由控制可用库存：主仓足够、备仓也足够，但应优先主仓
    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(
        self,
        session,
        platform,
        shop_id,
        warehouse_id,
        item_id,
    ):
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(
        ChannelInventoryService,
        "get_available_for_item",
        fake_get_available,
    )

    # 1) ingest：创建订单
    ext_order_no = "E-E2E-1"
    trace_id = "TRACE-E2E-PH4-001"
    occurred_at = datetime.now(timezone.utc)

    ingest_result = await OrderService.ingest(
        session,
        platform=platform,
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        occurred_at=occurred_at,
        buyer_name="张三",
        buyer_phone="13800000000",
        order_amount=50,
        pay_amount=50,
        items=[
            {
                "item_id": 1,
                "sku_id": "SKU-1",
                "title": "E2E 测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id=trace_id,
    )

    assert ingest_result["status"] == "OK"
    order_id = ingest_result["id"]
    order_ref = ingest_result["ref"]

    # 校验订单仓路由结果
    row = await session.execute(
        text("SELECT warehouse_id FROM orders WHERE id = :id"),
        {"id": order_id},
    )
    order_wh = row.scalar()
    assert order_wh == top_wid

    # 2) reserve：按同一个 ref 建立预占
    reserve_lines = [{"item_id": 1, "qty": 5}]
    reserve_result = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=order_ref,
        lines=reserve_lines,
        trace_id=trace_id,
    )
    assert reserve_result["status"] == "OK"

    # 校验 reservations.warehouse_id 与订单仓一致
    row = await session.execute(
        text(
            """
            SELECT warehouse_id
              FROM reservations
             WHERE platform = :p
               AND shop_id  = :s
               AND ref      = :r
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"p": platform.upper(), "s": shop_id, "r": order_ref},
    )
    res_wh = row.scalar()
    assert res_wh == order_wh == top_wid

    # 3) ship
    ship_lines = [
        ShipLine(
            item_id=1,
            batch_code="DEFAULT",
            qty=5,
            warehouse_id=order_wh,
        )
    ]

    svc = OutboundService()
    ship_result = await svc.commit(
        session=session,
        order_id=order_id,
        lines=ship_lines,
        occurred_at=datetime.now(timezone.utc),
        trace_id=trace_id,
    )

    assert isinstance(ship_result, dict)
    assert ship_result.get("order_id") == str(order_id)
    assert ship_result.get("status") == "OK"

    assert ship_result.get("committed_lines") == 0
    results = ship_result.get("results") or []
    assert isinstance(results, list)
    assert len(results) == 1
    assert "insufficient stock" in (results[0].get("error") or "")
