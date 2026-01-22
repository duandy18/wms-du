# tests/services/test_order_trace_phase4_routing.py
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.stock_availability_service import StockAvailabilityService
from app.services.order_service import OrderService

import app.services.order_ingest_service as order_ingest_service

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_two_warehouses(session):
    """
    返回两个 warehouse_id。
    若数量不足 2 个，则动态插入测试仓。
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

    while len(ids) < 2:
        row = await session.execute(
            text("INSERT INTO warehouses (name) VALUES (:name) RETURNING id"),
            {"name": f"AUTO-WH-{uuid.uuid4().hex[:8]}"},
        )
        ids.append(int(row.scalar()))

    return ids[0], ids[1]


async def _get_store_id_for_shop(session, platform: str, shop_id: str) -> int:
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
    assert store_id is not None, f"no store for {platform}/{shop_id}"
    return int(store_id)


async def _bind_store_warehouses_for_trace(
    session,
    *,
    platform: str,
    shop_id: str,
    top_warehouse_id: int,
    backup_warehouse_id: int,
):
    # legacy 配置保留：Route C 不使用 store_warehouse，但保留不影响
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
        {"sid": store_id, "wid": backup_warehouse_id, "top": False, "pr": 20},
    )


async def _ensure_service_province(session, *, province_code: str, warehouse_id: int) -> None:
    await session.execute(
        text("DELETE FROM warehouse_service_provinces WHERE province_code = :p"),
        {"p": province_code},
    )
    await session.execute(
        text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES (:wid, :p)
            """
        ),
        {"wid": int(warehouse_id), "p": province_code},
    )


async def test_warehouse_routed_audit_event_present(db_session_like_pg, monkeypatch):
    """
    Route C 审计语义：

    - 当订单满足“省命中服务仓 + 服务仓库存足够”时，
      ingest 之后应写入 WAREHOUSE_ROUTED 审计事件。
    - reason 不再是 auto_routed*，而是 service_hit。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    async def _noop_reserve_flow(*_, **__):
        return None

    monkeypatch.setattr(order_ingest_service, "reserve_flow", _noop_reserve_flow)

    top_wid, backup_wid = await _ensure_two_warehouses(session)
    await _bind_store_warehouses_for_trace(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    province = "P-TRACE"
    await _ensure_service_province(session, province_code=province, warehouse_id=top_wid)

    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(StockAvailabilityService, "get_available_for_item", fake_get_available)

    ext_order_no = "TRACE-EVT-1"
    trace_id = "TRACE-ROUTED-001"
    occurred_at = datetime.now(UTC)

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
                "title": "Trace 测试商品",
                "qty": 5,
                "price": 10,
                "discount": 0,
                "amount": 50,
            }
        ],
        address={"province": province, "receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id=trace_id,
    )

    assert ingest_result["status"] == "OK"
    order_ref = ingest_result["ref"]

    row = await session.execute(
        text(
            """
            SELECT meta
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND meta->>'event' = 'WAREHOUSE_ROUTED'
             ORDER BY created_at DESC
             LIMIT 1
            """
        ),
        {"ref": order_ref},
    )
    meta_obj = row.scalar()
    assert meta_obj is not None, "WAREHOUSE_ROUTED audit event not found"

    if isinstance(meta_obj, str):
        meta = json.loads(meta_obj)
    else:
        meta = meta_obj

    assert meta["platform"] == platform.upper()
    assert meta["shop"] == shop_id
    assert meta["warehouse_id"] == top_wid
    assert meta.get("reason") in ("service_hit", "auto_routed", "auto_routed_top", "auto_routed_best")
    assert top_wid in meta.get("considered", [])
