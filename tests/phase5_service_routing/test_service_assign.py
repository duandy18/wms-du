# tests/phase5_service_routing/test_service_assign.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services.order_service import OrderService

pytestmark = pytest.mark.asyncio


async def _ensure_service_province(session, *, warehouse_id: int, province_code: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO warehouse_service_provinces (warehouse_id, province_code)
            VALUES (:wid, :prov)
            ON CONFLICT (province_code) DO UPDATE
              SET warehouse_id = EXCLUDED.warehouse_id
            """
        ),
        {"wid": int(warehouse_id), "prov": str(province_code)},
    )


async def _ensure_city_split(session, *, province_code: str) -> None:
    # 如果表不存在，这条测试应当失败（说明迁移/种子不完整）
    await session.execute(
        text(
            """
            INSERT INTO warehouse_service_city_split_provinces (province_code)
            VALUES (:p)
            ON CONFLICT (province_code) DO NOTHING
            """
        ),
        {"p": str(province_code)},
    )


async def _ensure_service_city(session, *, warehouse_id: int, province_code: str, city_code: str) -> None:
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


async def _load_order_state(session, order_id: int) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  f.fulfillment_status AS fulfillment_status,
                  f.actual_warehouse_id AS warehouse_id,
                  f.planned_warehouse_id AS service_warehouse_id,
                  f.blocked_reasons AS blocked_reasons
                FROM orders o
                LEFT JOIN order_fulfillment f ON f.order_id = o.id
                WHERE o.id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()
    return dict(row) if row else {}


async def test_ingest_assigns_service_warehouse_by_province(db_session_like_pg, monkeypatch):
    """
    新主线：省级服务范围命中 → SERVICE_ASSIGNED（写 order_fulfillment.planned_warehouse_id，不写实际仓）
    """
    session = db_session_like_pg

    # baseline 里通常至少有一个仓
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wid = int(row.scalar_one())

    province = "UT-PROV-SVC"
    await _ensure_service_province(session, warehouse_id=wid, province_code=province)
    await session.commit()

    res = await OrderService.ingest(
        session,
        platform="PDD",
        shop_id="SVC-1",
        ext_order_no="SVC-PROV-1",
        occurred_at=datetime.now(timezone.utc),
        buyer_name="A",
        buyer_phone="111",
        order_amount=10,
        pay_amount=10,
        items=[{"item_id": 1, "qty": 1}],
        address={"province": province, "receiver_name": "A", "receiver_phone": "111"},
        extras={},
        trace_id="TRACE-SVC-PROV-1",
    )

    # Phase 5：命中服务仓应当不被 BLOCKED
    assert res["status"] in ("OK", "IDEMPOTENT"), res

    oid = int(res["id"])
    st = await _load_order_state(session, oid)

    assert str(st.get("fulfillment_status")) == "SERVICE_ASSIGNED"
    assert st.get("service_warehouse_id") == wid
    assert st.get("warehouse_id") in (None, 0)


async def test_ingest_blocks_when_city_split_but_city_missing(db_session_like_pg, monkeypatch):
    """
    Phase 5 合同（当前实现）：
    - 省启用 city-split 后：必须提供 city
    - 未提供 city 或 city 未配置服务仓：统一视为 “NO_SERVICE_WAREHOUSE”
    """
    session = db_session_like_pg

    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wid = int(row.scalar_one())

    province = "UT-PROV-SPLIT"
    await _ensure_city_split(session, province_code=province)
    await _ensure_service_city(session, warehouse_id=wid, province_code=province, city_code="UT-CITY-1")
    await session.commit()

    res = await OrderService.ingest(
        session,
        platform="PDD",
        shop_id="SVC-2",
        ext_order_no="SVC-CITY-MISS-1",
        occurred_at=datetime.now(timezone.utc),
        buyer_name="B",
        buyer_phone="222",
        order_amount=10,
        pay_amount=10,
        items=[{"item_id": 1, "qty": 1}],
        address={"province": province, "receiver_name": "B", "receiver_phone": "222"},
        extras={},
        trace_id="TRACE-SVC-CITY-MISS-1",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED", res
    assert isinstance(res.get("route"), dict), res
    # 当前实现：city-split 省缺 city => NO_SERVICE_WAREHOUSE
    assert res["route"].get("reason") == "NO_SERVICE_WAREHOUSE", res
    assert res["route"].get("mode") == "city", res
