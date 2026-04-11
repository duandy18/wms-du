# tests/api/test_v2_full_chain.py
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.order_service import OrderService
from app.wms.stock.services.lots import ensure_lot_full
from app.wms.stock.services.stock_service import StockService


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

    # 省路由 → 仓 1（仅为兼容旧测试数据，不作为主线依赖）
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


async def _ensure_supplier_lot(session: AsyncSession, *, wh_id: int, item_id: int, lot_code: str) -> int:
    """
    当前终态：
    - REQUIRED lot 身份 = (warehouse_id, item_id, production_date)
    - lot_code 只保留为展示/输入/追溯属性
    因此测试侧必须走统一入口 ensure_lot_full，并在 REQUIRED 商品下显式给 production_date。
    """
    return await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh_id),
        lot_code=str(lot_code),
        production_date=date.today(),
        expiry_date=None,
    )


async def _pick_active_shipping_provider_for_warehouse(
    session: AsyncSession,
    *,
    warehouse_id: int,
) -> dict[str, object] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  sp.id AS provider_id,
                  sp.code AS carrier_code,
                  sp.name AS carrier_name
                FROM warehouse_shipping_providers AS wsp
                JOIN shipping_providers AS sp
                  ON sp.id = wsp.shipping_provider_id
                WHERE wsp.warehouse_id = :wid
                  AND wsp.active = true
                  AND sp.active = true
                ORDER BY wsp.priority ASC, sp.priority ASC, sp.id ASC
                LIMIT 1
                """
            ),
            {"wid": warehouse_id},
        )
    ).mappings().first()

    return dict(row) if row else None


def _build_quote_snapshot(
    *,
    warehouse_id: int,
    provider_id: int,
    carrier_code: str | None,
    carrier_name: str | None,
    province: str,
    city: str,
    district: str,
    weight_kg: float,
) -> dict[str, object]:
    total_amount = 12.34
    base_amount = 10.84
    surcharge_amount = 1.50

    return {
        "version": "v1",
        "source": "unit-test",
        "input": {
            "warehouse_id": warehouse_id,
            "dest": {
                "province": province,
                "city": city,
                "district": district,
                "province_code": "UT-PROV-CODE",
                "city_code": "UT-CITY-CODE",
            },
            "real_weight_kg": weight_kg,
            "flags": [],
        },
        "selected_quote": {
            "quote_status": "OK",
            "template_id": 999001,
            "template_name": "UT-TEMPLATE",
            "provider_id": provider_id,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "currency": "CNY",
            "total_amount": total_amount,
            "weight": {
                "real_weight_kg": weight_kg,
                "billable_weight_kg": weight_kg,
            },
            "destination_group": {
                "group_id": 999001,
                "group_name": "UT-DEST-GROUP",
            },
            "pricing_matrix": {
                "matrix_id": 999001,
                "hit": True,
            },
            "breakdown": {
                "base": {
                    "amount": base_amount,
                },
                "surcharges": [
                    {
                        "id": 1,
                        "name": "UT-SURCHARGE",
                        "scope": "city",
                        "amount": surcharge_amount,
                        "detail": {"kind": "unit-test"},
                    }
                ],
                "summary": {
                    "base_amount": base_amount,
                    "surcharge_amount": surcharge_amount,
                    "extra_amount": surcharge_amount,
                    "total_amount": total_amount,
                },
            },
            "reasons": ["unit-test-selected-quote"],
        },
    }


async def _upsert_active_waybill_config(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    provider_id: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO electronic_waybill_configs (
                platform,
                shop_id,
                shipping_provider_id,
                customer_code,
                sender_name,
                sender_mobile,
                sender_phone,
                sender_province,
                sender_city,
                sender_district,
                sender_address,
                active,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :provider_id,
                'UT-CUSTOMER-CODE',
                'UT-SENDER',
                '13800000000',
                NULL,
                '北京市',
                '北京市',
                '朝阳区',
                '测试发件地址 FULL-CHAIN',
                TRUE,
                now(),
                now()
            )
            ON CONFLICT (platform, shop_id, shipping_provider_id) DO UPDATE
               SET customer_code = EXCLUDED.customer_code,
                   sender_name = EXCLUDED.sender_name,
                   sender_mobile = EXCLUDED.sender_mobile,
                   sender_phone = EXCLUDED.sender_phone,
                   sender_province = EXCLUDED.sender_province,
                   sender_city = EXCLUDED.sender_city,
                   sender_district = EXCLUDED.sender_district,
                   sender_address = EXCLUDED.sender_address,
                   active = TRUE,
                   updated_at = now()
            """
        ),
        {
            "platform": str(platform).upper(),
            "shop_id": str(shop_id),
            "provider_id": int(provider_id),
        },
    )


async def _load_order_id(
    session: AsyncSession,
    *,
    plat: str,
    shop_id: str,
    ext_order_no: str,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT id
            FROM orders
            WHERE platform = :platform
              AND shop_id = :shop_id
              AND ext_order_no = :ext_order_no
            LIMIT 1
            """
        ),
        {
            "platform": str(plat).upper(),
            "shop_id": str(shop_id),
            "ext_order_no": str(ext_order_no),
        },
    )
    order_id = row.scalar_one_or_none()
    assert order_id is not None, "order row not found after ingest"
    return int(order_id)


async def _upsert_prepare_package_for_ship(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    provider_id: int,
    weight_kg: float,
    quote_snapshot: dict[str, object],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare (
                order_id,
                address_ready_status,
                package_status,
                pricing_status,
                provider_status
            )
            VALUES (
                :order_id,
                'ready',
                'planned',
                'calculated',
                'selected'
            )
            ON CONFLICT (order_id) DO UPDATE SET
                address_ready_status = EXCLUDED.address_ready_status,
                package_status = EXCLUDED.package_status,
                pricing_status = EXCLUDED.pricing_status,
                provider_status = EXCLUDED.provider_status
            """
        ),
        {"order_id": int(order_id)},
    )

    await session.execute(
        text(
            """
            INSERT INTO order_shipment_prepare_packages (
                order_id,
                package_no,
                weight_kg,
                warehouse_id,
                pricing_status,
                selected_provider_id,
                selected_quote_snapshot
            )
            VALUES (
                :order_id,
                1,
                :weight_kg,
                :warehouse_id,
                'calculated',
                :provider_id,
                CAST(:quote_snapshot AS jsonb)
            )
            ON CONFLICT (order_id, package_no) DO UPDATE SET
                weight_kg = EXCLUDED.weight_kg,
                warehouse_id = EXCLUDED.warehouse_id,
                pricing_status = EXCLUDED.pricing_status,
                selected_provider_id = EXCLUDED.selected_provider_id,
                selected_quote_snapshot = EXCLUDED.selected_quote_snapshot,
                updated_at = now()
            """
        ),
        {
            "order_id": int(order_id),
            "weight_kg": float(weight_kg),
            "warehouse_id": int(warehouse_id),
            "provider_id": int(provider_id),
            "quote_snapshot": json.dumps(quote_snapshot, ensure_ascii=False),
        },
    )


@pytest.mark.asyncio
async def test_v2_order_full_chain(client: AsyncClient, db_session_like_pg: AsyncSession):
    """
    Phase 5+ 下的“订单驱动履约链”核心验收（当前主线）：

    1) ingest：创建订单并写 trace_id
    2) 人工履约决策：调用 manual-assign 指定执行仓，并标记可进入履约
    3) 入库（为后续 pick/ship 准备库存）
    4) pick → ship-with-waybill
    5) debug trace：至少出现 ORDER_CREATED + SHIPMENT/SHIP_COMMIT
    """
    plat = "PDD"
    shop_id = "1"
    uniq = uuid4().hex[:10]
    ext = f"ORD-TEST-3001-{uniq}"
    order_ref = f"ORD:{plat}:{shop_id}:{ext}"
    now = datetime.now(timezone.utc)

    province = "UT-PROV"
    city = "UT-CITY"
    district = "UT-DISTRICT"

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
        address={
            "province": province,
            "city": city,
            "district": district,
            "receiver_name": "X",
            "receiver_phone": "000",
        },
        extras=None,
        trace_id=trace_id,
    )
    await db_session_like_pg.commit()
    print(f"[TEST] ingest 返回: {r}")
    assert r["ref"] == order_ref

    order_id = await _load_order_id(
        db_session_like_pg,
        plat=plat,
        shop_id=shop_id,
        ext_order_no=ext,
    )

    # 2) manual-assign（需要登录；测试环境一般用 admin/admin123）
    login = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/fulfillment/manual-assign",
        json={"warehouse_id": 1, "reason": "UT assign", "note": "test"},
        headers=headers,
    )
    print("[HTTP] manual-assign status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OK"
    assert body["ref"] == order_ref
    assert int(body["to_warehouse_id"]) == 1

    # 3) 入库（Lot-World：必须锚定 lot_id）
    stock_svc = StockService()
    lot_code = "BATCH-001"
    lot_id = await _ensure_supplier_lot(db_session_like_pg, wh_id=1, item_id=3001, lot_code=lot_code)

    await stock_svc.adjust_lot(
        session=db_session_like_pg,
        item_id=3001,
        warehouse_id=1,
        lot_id=int(lot_id),
        delta=10,
        reason="RECEIPT",
        ref=f"UNIT-TEST-IN-3001-{uniq}",
        ref_line=1,
        occurred_at=now,
        batch_code=lot_code,
        production_date=now.date(),
        expiry_date=None,
        trace_id=None,
    )
    await db_session_like_pg.commit()
    print("[TEST] 已通过 StockService.adjust_lot 入库 10 件到 BATCH-001")

    # 4) pick（终态合同：batch_code 必须按行提供）
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/pick",
        json={
            "warehouse_id": 1,
            "lines": [{"item_id": 3001, "qty": 1, "batch_code": "BATCH-001"}],
        },
    )
    print("[HTTP] pick status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    pick_list = resp.json()
    assert isinstance(pick_list, list)
    assert len(pick_list) == 1

    provider = await _pick_active_shipping_provider_for_warehouse(db_session_like_pg, warehouse_id=1)
    if provider is None:
        pytest.skip("warehouse 1 has no active shipping provider binding")

    shipping_provider_id = int(provider["provider_id"])
    carrier_code = provider.get("carrier_code")
    carrier_name = provider.get("carrier_name")
    weight_kg = 1.0

    quote_snapshot = _build_quote_snapshot(
        warehouse_id=1,
        provider_id=shipping_provider_id,
        carrier_code=str(carrier_code) if carrier_code is not None else None,
        carrier_name=str(carrier_name) if carrier_name is not None else None,
        province=province,
        city=city,
        district=district,
        weight_kg=weight_kg,
    )

    await _upsert_prepare_package_for_ship(
        db_session_like_pg,
        order_id=order_id,
        warehouse_id=1,
        provider_id=shipping_provider_id,
        weight_kg=weight_kg,
        quote_snapshot=quote_snapshot,
    )
    await _upsert_active_waybill_config(
        db_session_like_pg,
        platform=plat,
        shop_id=shop_id,
        provider_id=shipping_provider_id,
    )
    await db_session_like_pg.commit()

    # 5) ship-with-waybill（Shipment Execution 唯一主入口）
    resp = await client.post(
        f"/orders/{plat}/{shop_id}/{ext}/ship-with-waybill",
        json={
            "package_no": 1,
            "receiver_name": "X",
            "receiver_phone": "000",
            "province": province,
            "city": city,
            "district": district,
            "address_detail": "UT-ADDR-001",
            "meta": {
                "extra": {
                    "source": "tests.api.test_v2_full_chain",
                },
            },
        },
        headers=headers,
    )
    print("[HTTP] ship-with-waybill status:", resp.status_code, "body:", resp.text)
    assert resp.status_code == 200, resp.text
    ship_data = resp.json()
    assert ship_data["ok"] is True
    assert ship_data["ref"] == order_ref
    assert int(ship_data["package_no"]) == 1
    assert int(ship_data["shipping_provider_id"]) == shipping_provider_id
    assert str(ship_data["tracking_no"]).strip() != ""
    assert ship_data["status"] == "IN_TRANSIT"

    # 6) trace
    trace_id2 = trace_id
    assert trace_id2

    # 7) trace
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
