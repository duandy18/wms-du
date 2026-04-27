from __future__ import annotations

from sqlalchemy import text
import pytest

from app.platform_order_ingestion.jd import router_ingest as jd_router_ingest
from app.platform_order_ingestion.jd.service_ingest import (
    JdOrderIngestPageResult,
    JdOrderIngestRowResult,
    JdOrderIngestService,
)
from app.platform_order_ingestion.jd.service_order_detail import (
    JdOrderDetail,
    JdOrderDetailItem,
)
from app.platform_order_ingestion.jd.service_real_pull import (
    JdOrderPageResult,
    JdOrderSummary,
    JdRealPullParams,
)

pytestmark = pytest.mark.asyncio

from app.main import app
from app.user.deps.auth import get_current_user


class _PlatformOrderIngestionPermissionUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True
    permissions = [
        "page.platform_order_ingestion.read",
        "page.platform_order_ingestion.write",
    ]


@pytest.fixture(autouse=True)
def _override_platform_order_ingestion_user():
    app.dependency_overrides[get_current_user] = lambda: _PlatformOrderIngestionPermissionUser()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)



async def _seed_jd_store(session, *, store_id: int = 8201) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (id, platform, store_code, store_name, active)
            VALUES (:id, 'jd', :store_code, :store_name, TRUE)
            ON CONFLICT (id) DO UPDATE
              SET platform = 'jd',
                  store_code = EXCLUDED.store_code,
                  store_name = EXCLUDED.store_name,
                  active = TRUE
            """
        ),
        {
            "id": store_id,
            "store_code": f"store-{store_id}",
            "store_name": f"store-{store_id}",
        },
    )
    await session.commit()


async def test_post_store_jd_orders_ingest_returns_page_result(client, monkeypatch):
    async def _fake_ingest_order_page(self, *, session, params):
        assert params.store_id == 123
        assert params.start_time == "2026-03-29 00:00:00"
        assert params.end_time == "2026-03-29 23:59:59"
        assert params.page == 1
        assert params.page_size == 20
        assert params.order_state == "WAIT_SELLER_STOCK_OUT"
        return JdOrderIngestPageResult(
            store_id=123,
            store_code="JD-STORE-123",
            page=1,
            page_size=20,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=False,
            start_time=params.start_time,
            end_time=params.end_time,
            rows=[
                JdOrderIngestRowResult(
                    order_id="JD-ORDER-001",
                    jd_order_id=9001,
                    status="OK",
                    error=None,
                ),
                JdOrderIngestRowResult(
                    order_id="JD-ORDER-002",
                    jd_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        jd_router_ingest.JdOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/jd/orders/ingest",
        json={
            "start_time": "2026-03-29 00:00:00",
            "end_time": "2026-03-29 23:59:59",
            "order_state": "WAIT_SELLER_STOCK_OUT",
            "page": 1,
            "page_size": 20,
        },
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["platform"] == "jd"
    assert data["store_id"] == 123
    assert data["store_code"] == "JD-STORE-123"
    assert data["orders_count"] == 2
    assert data["success_count"] == 1
    assert data["failed_count"] == 1
    assert data["rows"][0]["order_id"] == "JD-ORDER-001"
    assert data["rows"][0]["jd_order_id"] == 9001
    assert data["rows"][1]["status"] == "FAILED"


async def test_jd_order_ingest_service_persists_order_and_replaces_items(session, monkeypatch):
    store_id = 8201
    await _seed_jd_store(session, store_id=store_id)
    await session.execute(text("DELETE FROM jd_order_items"))
    await session.execute(text("DELETE FROM jd_orders WHERE store_id = :sid"), {"sid": store_id})
    await session.commit()

    async def _fake_fetch_order_page(self, *, session, params):
        assert params.store_id == store_id
        return JdOrderPageResult(
            page=params.page,
            page_size=params.page_size,
            orders_count=1,
            has_more=False,
            start_time=params.start_time or "2026-03-29 00:00:00",
            end_time=params.end_time or "2026-03-29 23:59:59",
            orders=[
                JdOrderSummary(
                    platform_order_id="JD-INGEST-8201",
                    order_state="WAIT_SELLER_STOCK_OUT",
                    order_type="SOP",
                    order_start_time="2026-03-29 12:00:00",
                    modified="2026-03-29 12:10:00",
                    consignee_name_masked="张三",
                    consignee_mobile_masked="13800138000",
                    consignee_address_summary_masked="上海市浦东新区测试路 1 号",
                    order_remark="请尽快发货",
                    order_total_price="128.50",
                    items_count=1,
                    raw_order={"order_id": "JD-INGEST-8201"},
                )
            ],
            raw_payload={"page": params.page},
        )

    async def _fake_fetch_order_detail(self, *, session, store_id: int, order_id: str):
        assert order_id == "JD-INGEST-8201"
        return JdOrderDetail(
            order_id="JD-INGEST-8201",
            vender_id="VENDER-8201",
            order_type="SOP",
            order_state="WAIT_SELLER_STOCK_OUT",
            buyer_pin="buyer-8201",
            consignee_name="张三",
            consignee_mobile="13800138000",
            consignee_phone=None,
            consignee_province="上海市",
            consignee_city="上海市",
            consignee_county="浦东新区",
            consignee_town="张江镇",
            consignee_address="测试路 1 号",
            order_remark="请尽快发货",
            seller_remark="测试备注",
            order_total_price="128.50",
            order_seller_price="120.00",
            freight_price="8.50",
            payment_confirm="true",
            order_start_time="2026-03-29 12:00:00",
            order_end_time=None,
            modified="2026-03-29 12:10:00",
            items=[
                JdOrderDetailItem(
                    sku_id="SKU-JD-8201",
                    outer_sku_id="OUTER-SKU-8201",
                    ware_id="WARE-8201",
                    item_name="京东测试商品A",
                    item_total=2,
                    item_price="39.90",
                    sku_name="颜色:黑;尺码:M",
                    gift_point=0,
                    raw_item={"sku_id": "SKU-JD-8201"},
                )
            ],
            raw_payload={"order_id": "JD-INGEST-8201"},
        )

    monkeypatch.setattr(
        "app.platform_order_ingestion.jd.service_ingest.JdRealPullService.fetch_order_page",
        _fake_fetch_order_page,
    )
    monkeypatch.setattr(
        "app.platform_order_ingestion.jd.service_ingest.JdOrderDetailService.fetch_order_detail",
        _fake_fetch_order_detail,
    )

    service = JdOrderIngestService()
    result = await service.ingest_order_page(
        session=session,
        params=JdRealPullParams(
            store_id=store_id,
            start_time="2026-03-29 00:00:00",
            end_time="2026-03-29 23:59:59",
            page=1,
            page_size=20,
            order_state="WAIT_SELLER_STOCK_OUT",
        ),
    )
    await session.commit()

    assert result.store_id == store_id
    assert result.store_code == f"store-{store_id}"
    assert result.orders_count == 1
    assert result.success_count == 1
    assert result.failed_count == 0
    assert result.rows[0].status == "OK"
    assert result.rows[0].jd_order_id is not None

    rows = (
        await session.execute(
            text(
                """
                SELECT o.order_id, o.order_state, o.order_total_price, i.sku_id, i.outer_sku_id, i.item_total
                  FROM jd_orders o
                  JOIN jd_order_items i ON i.jd_order_id = o.id
                 WHERE o.store_id = :sid
                   AND o.order_id = 'JD-INGEST-8201'
                """
            ),
            {"sid": store_id},
        )
    ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["order_id"] == "JD-INGEST-8201"
    assert rows[0]["order_state"] == "WAIT_SELLER_STOCK_OUT"
    assert str(rows[0]["order_total_price"]) == "128.50"
    assert rows[0]["sku_id"] == "SKU-JD-8201"
    assert rows[0]["outer_sku_id"] == "OUTER-SKU-8201"
    assert rows[0]["item_total"] == 2


async def test_post_store_jd_orders_ingest_returns_400_on_service_error(client, monkeypatch):
    async def _fake_ingest_order_page(self, *, session, params):
        raise jd_router_ingest.JdOrderIngestServiceError("jd pull failed: credential expired")

    monkeypatch.setattr(
        jd_router_ingest.JdOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/jd/orders/ingest",
        json={
            "start_time": "2026-03-29 00:00:00",
            "end_time": "2026-03-29 23:59:59",
            "page": 1,
            "page_size": 20,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "credential expired" in resp.text


async def test_post_store_jd_orders_ingest_rejects_invalid_page_size(client):
    resp = await client.post(
        "/oms/stores/123/jd/orders/ingest",
        json={"page_size": 0},
    )
    assert resp.status_code == 422, resp.text
