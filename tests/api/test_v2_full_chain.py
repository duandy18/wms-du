# tests/api/test_v2_full_chain.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_service import OrderService
from app.services.stock_service import StockService


async def _ensure_store_route_to_wh1(session: AsyncSession, *, plat: str, shop_id: str, province: str) -> None:
    """
    该 helper 保留用于历史/可读性：配置 store_warehouse + store_province_routes。
    Phase 5 的服务归属命中依赖 warehouse_service_provinces(/cities)，与 store_province_routes 无关。
    """
    await session.execute(
        text(
            """
            INSERT INTO stores (platform, shop_id, name)
            VALUES (:p,:s,:n)
            ON CONFLICT (platform, shop_id) DO NOTHING
            """
        ),
        {"p": plat.upper(), "s": shop_id, "n": f"UT-{plat.upper()}-{shop_id}"},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
        {"p": plat.upper(), "s": shop_id},
    )
    store_id = int(row.scalar_one())

    # 绑定仓 1
    await session.execute(
        text(
            """
            INSERT INTO store_warehouse (store_id, warehouse_id, is_top, priority)
            VALUES (:sid, 1, TRUE, 10)
            ON CONFLICT (store_id, warehouse_id) DO NOTHING
            """
        ),
        {"sid": store_id},
    )

    # 省路由 → 仓 1
    await session.execute(
        text("DELETE FROM store_province_routes WHERE store_id=:sid AND province=:prov"),
        {"sid": store_id, "prov": province},
    )
    await session.execute(
        text(
            """
            INSERT INTO store_province_routes (store_id, province, warehouse_id, priority, active)
            VALUES (:sid, :prov, 1, 10, TRUE)
            """
        ),
        {"sid": store_id, "prov": province},
    )


@pytest.mark.asyncio
async def test_v2_order_full_chain(client: AsyncClient, db_session_like_pg: AsyncSession):
    """
    Phase 5+（新世界观）下的“订单驱动履约链”核心验收：

    1) ingest：只写服务归属（SERVICE_ASSIGNED，写 service_warehouse_id，不写 warehouse_id）
    2) 人工履约决策：显式指定执行仓（warehouse_id / fulfillment_warehouse_id）并标记 READY_TO_FULFILL
    3) enter_pickable：调用 /orders/.../reserve（旧路由名保留，但语义已迁移为 enter_pickable）
       - 只生成 pick_task(+lines)/print_jobs
       - 不产生 reservation_id（字段不存在或为 None）
       - 不触库存
    4) 入库（为后续 pick/ship 准备库存）
    5) pick → ship_commit
    6) debug trace：不再出现 reservation_*，至少应出现 ORDER_CREATED + SHIPMENT/SHIP_COMMIT
    """
    plat = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext = f"ORD-TEST-3001-{uniq}"
    order_ref = f"ORD:{plat}:{shop_id}:{ext}"
    now = datetime.now(timezone.utc)

    province = "UT-PROV"
    await _ensure_store_route_to_wh1(db_session_like_pg, plat=plat, shop_id=shop_id, province=province)
    await db_session_like_pg.commit()

    trace_id = f"TEST-TRACE-ORDER-3001-{uniq}"

    print(f"[TEST] 准备订单 {order_ref}")

    # 1) 创建订单（必须带 province）
    r = await OrderService.ingest(
        db_session_like_pg,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=now,
        buyer_name="tester",
        buyer_phone="",
        order_amount=0,
        pay_amount=0,
        items=[{"item_id": 3001, "qty": 1, "title": "猫粮"}],
        address={"province": province, "receiver_name": "X", "receiver_phone": "000"},
        extras=None,
        trace_id=trace_id,
    )
    await db_session_like_pg.commit()
    print(f"[TEST] ingest 返回: {r}")
    assert r["ref"] == order_ref

    # Phase 5：ingest 只到 SERVICE_ASSIGNED，不自动写 warehouse_id
    # 人工决策层（最小可用）：显式指定执行仓 + 标记可进入履约
    await db_session_like_pg.execute(
        text(
            """
            UPDATE orders
               SET warehouse_id = 1,
                   fulfillment_warehouse_id = 1,
                   fulfillment_status = 'READY_TO_FULFILL',
                   blocked_reasons = NULL,
                   blocked_detail = NULL
             WHERE id = :oid
            """
        ),
        {"oid": int(r["id"])},
    )
    await db_session_like_pg.commit()

    # 2) enter_pickable：沿用旧路由名 /reserve，但新语义：只生成 pick_task，不产生 reservation
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/reserve",
        json={"lines": [{"item_id": 3001, "qty": 1}]},
    )
    print("[HTTP] reserve(enter_pickable) status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "OK"
    assert data["ref"] == order_ref
    # 新世界观：reservation_id 不应存在/不应非空
    assert data.get("reservation_id") is None
    assert data["lines"] == 1

    # 验证 enter_pickable 的产物：pick_task 一定存在（幂等）
    row_task = (
        await db_session_like_pg.execute(
            text(
                """
                SELECT id
                  FROM pick_tasks
                 WHERE ref = :ref AND warehouse_id = 1
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": order_ref},
        )
    ).first()
    assert row_task, "enter_pickable should create pick_task"
    task_id = int(row_task[0])
    assert task_id > 0

    # 3) 入库（为后续 pick/ship 准备库存）
    stock_svc = StockService()
    await stock_svc.adjust(
        session=db_session_like_pg,
        item_id=3001,
        delta=10,
        reason="RECEIPT",
        ref=f"UNIT-TEST-IN-3001-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code="BATCH-001",
        production_date=now.date(),
        warehouse_id=1,
        trace_id=None,
    )
    await db_session_like_pg.commit()
    print("[TEST] 已通过 StockService.adjust 入库 10 件到 BATCH-001")

    # 4) pick（沿用现状：订单驱动 pick API）
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/pick",
        json={
            "warehouse_id": 1,
            "batch_code": "BATCH-001",
            "lines": [{"item_id": 3001, "qty": 1}],
        },
    )
    print("[HTTP] pick status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    pick_list = resp.json()
    assert isinstance(pick_list, list)
    assert len(pick_list) == 1

    # 5) ship（沿用现状：订单驱动 ship API）
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/ship",
        json={
            "warehouse_id": 1,
            "lines": [{"item_id": 3001, "qty": 1}],
        },
    )
    print("[HTTP] ship status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    ship_data = resp.json()
    assert ship_data["ref"] == order_ref
    assert ship_data["event"] == "SHIP_COMMIT"
    assert ship_data["status"] in ("OK", "IDEMPOTENT")

    # 6) dev/orders
    resp = await client.get(f"/dev/orders/{plat}/{shop_id}/{ext}")
    assert resp.status_code == 200, resp.text
    ov = resp.json()
    print("[HTTP] dev/orders 返回:", json.dumps(ov, ensure_ascii=False))
    trace_id2 = ov.get("trace_id") or ov["order"]["trace_id"]
    assert trace_id2

    # 7) trace：新世界观断言（不再出现 reservation_*）
    resp = await client.get(f"/debug/trace/{trace_id2}")
    print("[HTTP] /debug/trace status:", resp.status_code)
    assert resp.status_code == 200, resp.text
    trace = resp.json()
    events = trace["events"]
    kinds = [e["kind"] for e in events]
    summaries = [e["summary"] for e in events]

    assert any("ORDER_CREATED" in s for s in summaries), summaries
    assert any(k == "SHIPMENT" for k in kinds), kinds
    assert any("SHIP_COMMIT" in s for s in summaries), summaries

    # 旧世界观：reservation_* 已死；如果还出现，说明 trace 聚合或事件发送有遗留
    assert not any(k.startswith("reservation_") or k == "reservation_line" for k in kinds), kinds


@pytest.mark.asyncio
async def test_v2_order_reserve_requires_warehouse(
    client: AsyncClient,
    db_session_like_pg: AsyncSession,
    monkeypatch,
):
    """
    没有 READY_TO_FULFILL / warehouse_id 的订单，调用订单驱动 enter_pickable（旧路由名 reserve）时应失败，
    防止“未定仓进入拣货流程”。
    """
    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    plat = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext = f"ORD-NO-WH-{uniq}"
    now = datetime.now(timezone.utc)

    # 不提供 province（应 FULFILLMENT_BLOCKED），enter_pickable 必须失败
    r = await OrderService.ingest(
        db_session_like_pg,
        platform=plat,
        shop_id=shop_id,
        ext_order_no=ext,
        occurred_at=now,
        buyer_name="tester",
        buyer_phone="",
        order_amount=0,
        pay_amount=0,
        items=[{"item_id": 3002, "qty": 1, "title": "测试品"}],
        address=None,
        extras=None,
        trace_id=f"TEST-TRACE-NO-WH-{uniq}",
    )
    await db_session_like_pg.commit()
    print("[TEST] ingest(no-wh) 返回:", r)

    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/reserve",
        json={"lines": [{"item_id": 3002, "qty": 1}]},
    )
    print("[HTTP] reserve(no-wh) status:", resp.status_code, "body:", resp.text)

    # 不强绑具体码：不同实现可能返回 409/422/500，但必须不是 200
    assert resp.status_code != 200

    body = resp.json()
    s = json.dumps(body, ensure_ascii=False)
    assert ("blocked" in s) or ("FULFILLMENT_BLOCKED" in s) or ("warehouse_id" in s) or ("insufficient" in s), s
