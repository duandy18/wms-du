from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential
from app.platform_order_ingestion.models.taobao_app_config import TaobaoAppConfig
from app.platform_order_ingestion.taobao.contracts import TaobaoTopResponse
from app.platform_order_ingestion.taobao import service_order_detail as detail_module
from app.platform_order_ingestion.taobao import service_real_pull as real_pull_module
from app.platform_order_ingestion.taobao.service_order_detail import TaobaoOrderDetailService
from app.platform_order_ingestion.taobao.service_real_pull import (
    TaobaoRealPullParams,
    TaobaoRealPullService,
    TaobaoRealPullServiceError,
)

pytestmark = pytest.mark.asyncio


async def _seed_store(session, *, store_id: int = 8401) -> None:
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


async def _clear_taobao_state(session) -> None:
    await session.execute(text("DELETE FROM store_platform_connections WHERE platform = 'taobao'"))
    await session.execute(text("DELETE FROM store_platform_credentials WHERE platform = 'taobao'"))
    await session.execute(text("DELETE FROM taobao_app_configs"))
    await session.commit()


async def _seed_app_and_credential(session, *, store_id: int = 8401) -> None:
    now = datetime.now(timezone.utc)
    await _seed_store(session, store_id=store_id)
    session.add(
        TaobaoAppConfig(
            app_key="taobao-app-key",
            app_secret="taobao-app-secret",
            callback_url="http://127.0.0.1:8000/oms/taobao/oauth/callback",
            api_base_url="https://eco.taobao.com/router/rest",
            sign_method="md5",
            is_enabled=True,
        )
    )
    session.add(
        StorePlatformCredential(
            store_id=store_id,
            platform="taobao",
            credential_type="oauth",
            access_token="taobao-session-token",
            refresh_token="taobao-refresh-token",
            expires_at=now + timedelta(days=1),
            scope="taobao.trades.sold.get,taobao.trade.fullinfo.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="taobao_user_id",
            granted_identity_value="tb-user-8401",
            granted_identity_display="tb-shop-8401",
        )
    )
    await session.commit()


async def test_fetch_order_page_requires_both_time_values(session):
    service = TaobaoRealPullService()

    with pytest.raises(TaobaoRealPullServiceError, match="both provided"):
        await service.fetch_order_page(
            session=session,
            params=TaobaoRealPullParams(
                store_id=8401,
                start_time="2026-03-29 00:00:00",
                end_time=None,
            ),
        )


async def test_fetch_order_page_rejects_window_too_large(session):
    service = TaobaoRealPullService()

    with pytest.raises(TaobaoRealPullServiceError, match="<= 30 days"):
        await service.fetch_order_page(
            session=session,
            params=TaobaoRealPullParams(
                store_id=8401,
                start_time="2026-01-01 00:00:00",
                end_time="2026-03-01 00:00:00",
            ),
        )


async def test_fetch_order_page_rejects_missing_credential(session):
    await _clear_taobao_state(session)
    await _seed_store(session, store_id=8402)
    session.add(
        TaobaoAppConfig(
            app_key="taobao-app-key",
            app_secret="taobao-app-secret",
            callback_url="http://127.0.0.1:8000/oms/taobao/oauth/callback",
            api_base_url="https://eco.taobao.com/router/rest",
            sign_method="md5",
            is_enabled=True,
        )
    )
    await session.commit()

    service = TaobaoRealPullService()
    with pytest.raises(TaobaoRealPullServiceError, match="credential not found"):
        await service.fetch_order_page(
            session=session,
            params=TaobaoRealPullParams(
                store_id=8402,
                start_time="2026-03-29 00:00:00",
                end_time="2026-03-29 23:59:59",
            ),
        )


async def test_fetch_order_page_success_parses_trades(session, monkeypatch):
    await _clear_taobao_state(session)
    await _seed_app_and_credential(session, store_id=8403)

    captured = {}

    class _FakeTopClient:
        def __init__(self, *, config):
            captured["config_app_key"] = config.app_key

        async def call(self, request):
            captured["method"] = request.method
            captured["session"] = request.session
            captured["biz_params"] = dict(request.biz_params)

            return TaobaoTopResponse(
                raw={"taobao_trades_sold_get_response": {"ok": True}},
                body={
                    "total_results": 1,
                    "has_next": False,
                    "trades": {
                        "trade": [
                            {
                                "tid": "TB-ORDER-8403",
                                "status": "WAIT_SELLER_SEND_GOODS",
                                "type": "fixed",
                                "buyer_nick": "buyer-demo",
                                "buyer_open_uid": "ou-demo",
                                "receiver_name": "张三",
                                "receiver_mobile": "13800138000",
                                "receiver_state": "上海",
                                "receiver_city": "上海市",
                                "receiver_district": "浦东新区",
                                "receiver_town": "张江镇",
                                "receiver_address": "科苑路 88 号",
                                "payment": "99",
                                "total_fee": "109.00",
                                "post_fee": "10",
                                "seller_flag": "1",
                                "created": "2026-03-29 12:00:00",
                                "pay_time": "2026-03-29 12:05:00",
                                "modified": "2026-03-29 12:10:00",
                                "orders": {
                                    "order": [
                                        {
                                            "oid": "TB-OID-8403",
                                            "outer_sku_id": "OUTER-SKU-8403",
                                        }
                                    ]
                                },
                            }
                        ]
                    },
                },
            )

    monkeypatch.setattr(real_pull_module, "TaobaoTopClient", _FakeTopClient)

    service = TaobaoRealPullService()
    result = await service.fetch_order_page(
        session=session,
        params=TaobaoRealPullParams(
            store_id=8403,
            start_time="2026-03-29 00:00:00",
            end_time="2026-03-29 23:59:59",
            status="WAIT_SELLER_SEND_GOODS",
            page=2,
            page_size=50,
        ),
    )

    assert captured["config_app_key"] == "taobao-app-key"
    assert captured["method"] == "taobao.trades.sold.get"
    assert captured["session"] == "taobao-session-token"
    assert captured["biz_params"]["start_created"] == "2026-03-28 23:59:00"
    assert captured["biz_params"]["end_created"] == "2026-03-29 23:59:59"
    assert captured["biz_params"]["status"] == "WAIT_SELLER_SEND_GOODS"
    assert captured["biz_params"]["page_no"] == 2
    assert captured["biz_params"]["page_size"] == 50
    assert "fields" in captured["biz_params"]

    assert result.page == 2
    assert result.page_size == 50
    assert result.orders_count == 1
    assert result.has_more is False
    assert result.orders[0].tid == "TB-ORDER-8403"
    assert result.orders[0].status == "WAIT_SELLER_SEND_GOODS"
    assert result.orders[0].payment == "99.00"
    assert result.orders[0].seller_flag == 1
    assert result.orders[0].items_count == 1


async def test_fetch_order_detail_success_parses_items(session, monkeypatch):
    await _clear_taobao_state(session)
    await _seed_app_and_credential(session, store_id=8404)

    captured = {}

    class _FakeTopClient:
        def __init__(self, *, config):
            captured["config_app_key"] = config.app_key

        async def call(self, request):
            captured["method"] = request.method
            captured["session"] = request.session
            captured["biz_params"] = dict(request.biz_params)

            return TaobaoTopResponse(
                raw={"taobao_trade_fullinfo_get_response": {"ok": True}},
                body={
                    "trade": {
                        "tid": "TB-DETAIL-8404",
                        "status": "WAIT_SELLER_SEND_GOODS",
                        "type": "fixed",
                        "buyer_nick": "buyer-demo",
                        "buyer_open_uid": "ou-demo",
                        "receiver_name": "李四",
                        "receiver_mobile": "13900139000",
                        "receiver_phone": "021-12345678",
                        "receiver_state": "浙江",
                        "receiver_city": "杭州市",
                        "receiver_district": "西湖区",
                        "receiver_town": "转塘街道",
                        "receiver_address": "云栖小镇 18 号",
                        "receiver_zip": "310000",
                        "buyer_memo": "请尽快发货",
                        "buyer_message": "晚上可收件",
                        "seller_memo": "测试备注",
                        "seller_flag": "2",
                        "payment": "99",
                        "total_fee": "109",
                        "post_fee": "10",
                        "coupon_fee": "5",
                        "created": "2026-03-29 12:00:00",
                        "pay_time": "2026-03-29 12:05:00",
                        "modified": "2026-03-29 12:10:00",
                        "orders": {
                            "order": [
                                {
                                    "oid": "TB-OID-8404",
                                    "num_iid": "NUMIID8404",
                                    "sku_id": "SKUID8404",
                                    "outer_iid": "OUTER-ITEM-8404",
                                    "outer_sku_id": "OUTER-SKU-8404",
                                    "title": "淘宝测试商品",
                                    "price": "99",
                                    "num": "1",
                                    "payment": "99",
                                    "total_fee": "99",
                                    "sku_properties_name": "颜色:黑色;尺寸:XL",
                                }
                            ]
                        },
                    }
                },
            )

    monkeypatch.setattr(detail_module, "TaobaoTopClient", _FakeTopClient)

    service = TaobaoOrderDetailService()
    result = await service.fetch_order_detail(
        session=session,
        store_id=8404,
        tid="TB-DETAIL-8404",
    )

    assert captured["method"] == "taobao.trade.fullinfo.get"
    assert captured["session"] == "taobao-session-token"
    assert captured["biz_params"]["tid"] == "TB-DETAIL-8404"
    assert "fields" in captured["biz_params"]

    assert result.tid == "TB-DETAIL-8404"
    assert result.status == "WAIT_SELLER_SEND_GOODS"
    assert result.receiver_name == "李四"
    assert result.payment == "99.00"
    assert result.total_fee == "109.00"
    assert result.post_fee == "10.00"
    assert result.coupon_fee == "5.00"
    assert result.seller_flag == 2
    assert result.items is not None
    assert len(result.items) == 1
    assert result.items[0].oid == "TB-OID-8404"
    assert result.items[0].outer_sku_id == "OUTER-SKU-8404"
    assert result.items[0].price == "99.00"
    assert result.items[0].num == 1
    assert result.items[0].payment == "99.00"
