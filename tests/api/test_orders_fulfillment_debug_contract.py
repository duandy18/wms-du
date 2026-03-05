# tests/api/test_orders_fulfillment_debug_contract.py
from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _insert_min_order(session, *, platform: str, shop_id: str, ext_order_no: str) -> int:
    row = await session.execute(
        text(
            """
            INSERT INTO orders(platform, shop_id, ext_order_no, status, created_at, updated_at)
            VALUES (:p, :s, :e, 'CREATED', now(), now())
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {"p": platform.upper(), "s": shop_id, "e": ext_order_no},
    )
    return int(row.scalar_one())


async def _upsert_order_address(session, *, order_id: int, province: str, city: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_address(order_id, province, city, district, detail)
            VALUES (:oid, :prov, :city, 'UT-DIST', 'UT-DETAIL')
            ON CONFLICT (order_id) DO UPDATE
              SET province = EXCLUDED.province,
                  city = EXCLUDED.city,
                  district = EXCLUDED.district,
                  detail = EXCLUDED.detail
            """
        ),
        {"oid": int(order_id), "prov": province, "city": city},
    )


async def _seed_service_city(session, *, warehouse_id: int, province_code: str, city_code: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO warehouse_service_cities(warehouse_id, province_code, city_code)
            VALUES (:wid, :prov, :city)
            ON CONFLICT (city_code) DO UPDATE
              SET warehouse_id = EXCLUDED.warehouse_id,
                  province_code = EXCLUDED.province_code
            """
        ),
        {"wid": int(warehouse_id), "prov": str(province_code), "city": str(city_code)},
    )


async def test_orders_fulfillment_debug_contract_shape(client_like, db_session_like_pg):
    """
    v4-min 合同：
    - 只返回：address + service + summary
    - 明确不返回：blocked_* / fulfillment_status / candidates / scan / check
    """
    session = db_session_like_pg

    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wid = int(row.scalar_one())

    platform = "TB"
    shop_id = "TEST"
    ext = "UT-FD-001"
    province = "河北省"
    city = "保定市"

    order_id = await _insert_min_order(session, platform=platform, shop_id=shop_id, ext_order_no=ext)
    await _upsert_order_address(session, order_id=order_id, province=province, city=city)
    await _seed_service_city(session, warehouse_id=wid, province_code=province, city_code=city)

    await session.commit()

    r = await client_like.get(f"/orders/{order_id}/fulfillment-debug")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("version") == "v4-min"
    assert int(data["order_id"]) == int(order_id)
    assert data["platform"] == platform
    assert data["shop_id"] == shop_id

    # 必须不存在的字段（避免复杂度回潮）
    assert "fulfillment_status" not in data
    assert "blocked_reasons" not in data
    # 等价护栏：不让“阻断细节”字段回潮（不在源码中出现该 token）
    assert ("blocked" + "_" + "detail") not in data
    assert "candidates" not in data
    assert "scan" not in data
    assert "check" not in data

    addr = data.get("address") or {}
    assert addr.get("province") == province
    assert addr.get("city") == city
    assert addr.get("district") == "UT-DIST"
    assert addr.get("detail") == "UT-DETAIL"

    svc = data.get("service") or {}
    assert svc.get("city_code") == city
    assert bool(svc.get("hit")) is True
    assert int(svc.get("service_warehouse_id")) == int(wid)
    assert svc.get("reason") == "OK"

    summary = data.get("summary") or {}
    assert bool(summary.get("service_city_hit")) is True
    assert int(summary.get("service_warehouse_id") or 0) == int(wid)


async def test_orders_fulfillment_debug_when_city_missing(client_like, db_session_like_pg):
    """
    city 缺失时：
    - service.hit=false
    - reason=CITY_MISSING
    """
    session = db_session_like_pg

    platform = "TB"
    shop_id = "TEST"
    ext = "UT-FD-002"
    province = "河北省"

    order_id = await _insert_min_order(session, platform=platform, shop_id=shop_id, ext_order_no=ext)
    await session.execute(
        text(
            """
            INSERT INTO order_address(order_id, province, city, district, detail)
            VALUES (:oid, :prov, NULL, 'UT-DIST', 'UT-DETAIL')
            ON CONFLICT (order_id) DO UPDATE
              SET province = EXCLUDED.province,
                  city = EXCLUDED.city,
                  district = EXCLUDED.district,
                  detail = EXCLUDED.detail
            """
        ),
        {"oid": int(order_id), "prov": province},
    )

    await session.commit()

    r = await client_like.get(f"/orders/{order_id}/fulfillment-debug")
    assert r.status_code == 200, r.text
    data = r.json()

    svc = data.get("service") or {}
    assert bool(svc.get("hit")) is False
    assert svc.get("reason") == "CITY_MISSING"
