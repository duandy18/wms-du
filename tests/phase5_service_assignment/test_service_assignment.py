# tests/phase5_service_assignment/test_service_assignment.py
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.order_service import OrderService

pytestmark = pytest.mark.asyncio


async def _pick_any_item_id(session) -> int:
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    iid = row.scalar_one_or_none()
    if iid is None:
        raise RuntimeError("tests baseline seed 没有 items，无法跑 service_assignment tests")
    return int(iid)


async def _pick_any_warehouse_id(session) -> int:
    row = await session.execute(text("SELECT id FROM warehouses ORDER BY id ASC LIMIT 1"))
    wid = row.scalar_one_or_none()
    if wid is None:
        raise RuntimeError("tests baseline seed 没有 warehouses，无法跑 service_assignment tests")
    return int(wid)


async def _seed_service_province(session, *, warehouse_id: int, province_code: str) -> None:
    # 依赖 province_code 全局唯一（你的库就是这么建的）
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


async def test_ingest_blocks_when_province_missing(db_session_like_pg, monkeypatch):
    session = db_session_like_pg

    # 明确关掉测试兜底（如果你 conftest 里还 setdefault 了默认省）
    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)

    item_id = await _pick_any_item_id(session)

    res = await OrderService.ingest(
        session,
        platform="TB",
        shop_id="TEST",
        ext_order_no="UT-SA-001",
        occurred_at=None,
        buyer_name="A",
        buyer_phone="1",
        order_amount=1,
        pay_amount=1,
        items=[{"item_id": item_id, "qty": 1, "sku_id": f"SKU-{item_id}", "title": "X"}],
        address={"receiver_name": "A", "receiver_phone": "1"},  # no province
        extras={},
        trace_id="TRACE-SA-001",
    )

    assert res["status"] == "FULFILLMENT_BLOCKED"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("reason") == "PROVINCE_MISSING_OR_INVALID"


async def test_ingest_assigns_service_warehouse_by_province(db_session_like_pg, monkeypatch):
    session = db_session_like_pg

    monkeypatch.delenv("WMS_TEST_DEFAULT_PROVINCE", raising=False)
    monkeypatch.delenv("WMS_TEST_DEFAULT_CITY", raising=False)

    item_id = await _pick_any_item_id(session)
    wh_id = await _pick_any_warehouse_id(session)

    province = "河北省"
    await _seed_service_province(session, warehouse_id=wh_id, province_code=province)
    await session.commit()

    res = await OrderService.ingest(
        session,
        platform="TB",
        shop_id="TEST",
        ext_order_no="UT-SA-002",
        occurred_at=None,
        buyer_name="B",
        buyer_phone="2",
        order_amount=1,
        pay_amount=1,
        items=[{"item_id": item_id, "qty": 1, "sku_id": f"SKU-{item_id}", "title": "X"}],
        address={"province": province, "receiver_name": "B", "receiver_phone": "2"},
        extras={},
        trace_id="TRACE-SA-002",
    )

    assert res["status"] == "OK"
    assert isinstance(res.get("route"), dict)
    assert res["route"].get("status") == "SERVICE_ASSIGNED"
    assert int(res["route"].get("service_warehouse_id")) == int(wh_id)

    order_id = int(res["id"])
    row = await session.execute(
        text("SELECT service_warehouse_id, warehouse_id, fulfillment_status FROM orders WHERE id=:id"),
        {"id": order_id},
    )
    swid, wid, fstat = row.first()
    assert int(swid) == int(wh_id)
    # ✅ 新世界观：不自动写实际出库仓
    assert wid in (None, 0)
    assert str(fstat) == "SERVICE_ASSIGNED"
