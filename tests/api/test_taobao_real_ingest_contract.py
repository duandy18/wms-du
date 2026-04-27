from __future__ import annotations

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.taobao import router_ingest as taobao_router_ingest
from app.platform_order_ingestion.taobao.service_ingest import (
    TaobaoOrderIngestPageResult,
    TaobaoOrderIngestRowResult,
    TaobaoOrderIngestService,
)
from app.platform_order_ingestion.taobao.service_order_detail import (
    TaobaoOrderDetail,
    TaobaoOrderDetailItem,
)
from app.platform_order_ingestion.taobao.service_real_pull import (
    TaobaoOrderPageResult,
    TaobaoOrderSummary,
    TaobaoRealPullParams,
)

pytestmark = pytest.mark.asyncio


async def _seed_taobao_store(session, *, store_id: int = 8601) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (id, platform, store_code, store_name, active)
            VALUES (:id, 'taobao', :store_code, :store_name, TRUE)
            ON CONFLICT (id) DO UPDATE
              SET platform = 'taobao',
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


async def test_post_store_taobao_orders_ingest_returns_page_result(client, monkeypatch):
    async def _fake_ingest_order_page(self, *, session, params):
        assert params.store_id == 123
        assert params.start_time == "2026-03-29 00:00:00"
        assert params.end_time == "2026-03-29 23:59:59"
        assert params.status == "WAIT_SELLER_SEND_GOODS"
        assert params.page == 1
        assert params.page_size == 50
        return TaobaoOrderIngestPageResult(
            store_id=123,
            store_code="TAOBAO-STORE-123",
            page=1,
            page_size=50,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=False,
            start_time=params.start_time,
            end_time=params.end_time,
            rows=[
                TaobaoOrderIngestRowResult(
                    tid="TB-ORDER-001",
                    taobao_order_id=9001,
                    status="OK",
                    error=None,
                ),
                TaobaoOrderIngestRowResult(
                    tid="TB-ORDER-002",
                    taobao_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        taobao_router_ingest.TaobaoOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/taobao/orders/ingest",
        json={
            "start_time": "2026-03-29 00:00:00",
            "end_time": "2026-03-29 23:59:59",
            "status": "WAIT_SELLER_SEND_GOODS",
            "page": 1,
            "page_size": 50,
        },
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["platform"] == "taobao"
    assert data["store_id"] == 123
    assert data["store_code"] == "TAOBAO-STORE-123"
    assert data["orders_count"] == 2
    assert data["success_count"] == 1
    assert data["failed_count"] == 1
    assert data["rows"][0]["tid"] == "TB-ORDER-001"
    assert data["rows"][0]["taobao_order_id"] == 9001
    assert data["rows"][1]["status"] == "FAILED"


async def test_taobao_order_ingest_service_persists_order_and_replaces_items(session, monkeypatch):
    store_id = 8601
    await _seed_taobao_store(session, store_id=store_id)
    await session.execute(text("DELETE FROM taobao_order_items"))
    await session.execute(text("DELETE FROM taobao_orders WHERE store_id = :sid"), {"sid": store_id})
    await session.commit()

    async def _fake_fetch_order_page(self, *, session, params):
        assert params.store_id == store_id
        return TaobaoOrderPageResult(
            page=params.page,
            page_size=params.page_size,
            orders_count=1,
            has_more=False,
            start_time=params.start_time or "2026-03-29 00:00:00",
            end_time=params.end_time or "2026-03-29 23:59:59",
            orders=[
                TaobaoOrderSummary(
                    tid="TB-INGEST-8601",
                    status="WAIT_SELLER_SEND_GOODS",
                    type="fixed",
                    buyer_nick="buyer-8601",
                    buyer_open_uid="ou-8601",
                    receiver_name="张三",
                    receiver_mobile="13800138000",
                    receiver_state="上海",
                    receiver_city="上海市",
                    receiver_district="浦东新区",
                    receiver_town="张江镇",
                    receiver_address="测试路 1 号",
                    payment="99.00",
                    total_fee="109.00",
                    post_fee="10.00",
                    created="2026-03-29 12:00:00",
                    pay_time="2026-03-29 12:05:00",
                    modified="2026-03-29 12:10:00",
                    items_count=1,
                    raw_order={"tid": "TB-INGEST-8601"},
                )
            ],
            raw_payload={"page": params.page},
        )

    async def _fake_fetch_order_detail(self, *, session, store_id: int, tid: str):
        assert tid == "TB-INGEST-8601"
        return TaobaoOrderDetail(
            tid="TB-INGEST-8601",
            status="WAIT_SELLER_SEND_GOODS",
            type="fixed",
            buyer_nick="buyer-8601",
            buyer_open_uid="ou-8601",
            receiver_name="张三",
            receiver_mobile="13800138000",
            receiver_phone=None,
            receiver_state="上海",
            receiver_city="上海市",
            receiver_district="浦东新区",
            receiver_town="张江镇",
            receiver_address="测试路 1 号",
            receiver_zip=None,
            buyer_memo="请尽快发货",
            buyer_message=None,
            seller_memo="测试备注",
            seller_flag=1,
            payment="99.00",
            total_fee="109.00",
            post_fee="10.00",
            coupon_fee="0.00",
            created="2026-03-29 12:00:00",
            pay_time="2026-03-29 12:05:00",
            modified="2026-03-29 12:10:00",
            items=[
                TaobaoOrderDetailItem(
                    oid="TB-OID-8601",
                    num_iid="NUMIID8601",
                    sku_id="SKUID8601",
                    outer_iid="OUTER-ITEM-8601",
                    outer_sku_id="OUTER-SKU-8601",
                    title="淘宝测试商品",
                    price="99.00",
                    num=2,
                    payment="99.00",
                    total_fee="99.00",
                    sku_properties_name="颜色:黑色",
                    raw_item={"oid": "TB-OID-8601"},
                )
            ],
            raw_payload={"tid": "TB-INGEST-8601"},
        )

    monkeypatch.setattr(
        "app.platform_order_ingestion.taobao.service_ingest.TaobaoRealPullService.fetch_order_page",
        _fake_fetch_order_page,
    )
    monkeypatch.setattr(
        "app.platform_order_ingestion.taobao.service_ingest.TaobaoOrderDetailService.fetch_order_detail",
        _fake_fetch_order_detail,
    )

    service = TaobaoOrderIngestService()
    result = await service.ingest_order_page(
        session=session,
        params=TaobaoRealPullParams(
            store_id=store_id,
            start_time="2026-03-29 00:00:00",
            end_time="2026-03-29 23:59:59",
            page=1,
            page_size=50,
            status="WAIT_SELLER_SEND_GOODS",
        ),
    )
    await session.commit()

    assert result.store_id == store_id
    assert result.store_code == f"store-{store_id}"
    assert result.orders_count == 1
    assert result.success_count == 1
    assert result.failed_count == 0
    assert result.rows[0].status == "OK"
    assert result.rows[0].taobao_order_id is not None

    rows = (
        await session.execute(
            text(
                """
                SELECT o.tid, o.status, o.payment, i.oid, i.outer_sku_id, i.num
                  FROM taobao_orders o
                  JOIN taobao_order_items i ON i.taobao_order_id = o.id
                 WHERE o.store_id = :sid
                   AND o.tid = 'TB-INGEST-8601'
                """
            ),
            {"sid": store_id},
        )
    ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["tid"] == "TB-INGEST-8601"
    assert rows[0]["status"] == "WAIT_SELLER_SEND_GOODS"
    assert str(rows[0]["payment"]) == "99.00"
    assert rows[0]["oid"] == "TB-OID-8601"
    assert rows[0]["outer_sku_id"] == "OUTER-SKU-8601"
    assert rows[0]["num"] == 2


async def test_post_store_taobao_orders_ingest_returns_400_on_service_error(client, monkeypatch):
    async def _fake_ingest_order_page(self, *, session, params):
        raise taobao_router_ingest.TaobaoOrderIngestServiceError("taobao pull failed: credential expired")

    monkeypatch.setattr(
        taobao_router_ingest.TaobaoOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/taobao/orders/ingest",
        json={
            "start_time": "2026-03-29 00:00:00",
            "end_time": "2026-03-29 23:59:59",
            "page": 1,
            "page_size": 50,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "credential expired" in resp.text


async def test_post_store_taobao_orders_ingest_rejects_invalid_page_size(client):
    resp = await client.post(
        "/oms/stores/123/taobao/orders/ingest",
        json={"page_size": 0},
    )
    assert resp.status_code == 422, resp.text
