# tests/services/test_order_trace_phase4_routing.py
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


async def _ensure_two_warehouses(session):
    """
    返回两个 warehouse_id。
    若数量不足 2 个，则动态插入测试仓（填充 NOT NULL 列）。
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
            text("INSERT INTO warehouses DEFAULT VALUES RETURNING id")
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


@pytest.mark.xfail(
    reason=(
        "WAREHOUSE_ROUTED audit event 尚未在当前实现中落地；"
        "该测试保留为 Phase 4 路由审计的规划，用于未来实现到位后启用。"
    ),
    strict=False,
)
@pytest.mark.asyncio
async def test_warehouse_routed_audit_event_present(db_session_like_pg, monkeypatch):
    """
    计划中的合同（当前实现尚未完全达成）：

      ingest 之后，audit_events 中存在一条 WAREHOUSE_ROUTED 事件，
      meta 中包含选中仓、platform/shop、trace_id 等信息。

    目前代码尚未写入该事件，因此本测试标记为 xfail，保留为未来演进目标。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S1"

    top_wid, backup_wid = await _ensure_two_warehouses(session)
    await _bind_store_warehouses_for_trace(
        session,
        platform=platform,
        shop_id=shop_id,
        top_warehouse_id=top_wid,
        backup_warehouse_id=backup_wid,
    )

    # 路由可用库存控制：两个仓都有货，但应优先 top_wid
    stock_map = {
        (top_wid, 1): 10,
        (backup_wid, 1): 10,
    }

    async def fake_get_available(self, *_, **kwargs):
        warehouse_id = kwargs.get("warehouse_id")
        item_id = kwargs.get("item_id")
        return int(stock_map.get((warehouse_id, item_id), 0))

    monkeypatch.setattr(ChannelInventoryService, "get_available_for_item", fake_get_available)

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
        address={"receiver_name": "张三", "receiver_phone": "13800000000"},
        extras={},
        trace_id=trace_id,
    )

    assert ingest_result["status"] == "OK"
    order_ref = ingest_result["ref"]

    # 查 audit_events，看是否存在 WAREHOUSE_ROUTED
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
    # 现在实现中 meta_obj 很可能为 None，从而触发 xfail
    assert meta_obj is not None, "WAREHOUSE_ROUTED audit event not found"

    # meta 可能是 jsonb → dict，也可能是 text → str
    if isinstance(meta_obj, str):
        meta = json.loads(meta_obj)
    else:
        meta = meta_obj  # 已经是 dict

    assert meta["platform"] == platform.upper()
    assert meta["shop"] == shop_id
    assert meta["warehouse_id"] == top_wid
    assert meta.get("reason", "").startswith("auto_routed")
    assert top_wid in meta.get("considered", [])
    if trace_id:
        assert meta.get("trace_id") == trace_id
