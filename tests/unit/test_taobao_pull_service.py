from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential
from app.platform_order_ingestion.taobao import service_pull as taobao_pull_module
from app.platform_order_ingestion.taobao.service_order_detail import (
    TaobaoOrderDetail,
    TaobaoOrderDetailItem,
)
from app.platform_order_ingestion.taobao.service_pull import TaobaoPullService
from app.platform_order_ingestion.taobao.service_real_pull import (
    TaobaoOrderPageResult,
    TaobaoOrderSummary,
    TaobaoRealPullServiceError,
)
from app.platform_order_ingestion.taobao.settings import TaobaoTopConfig

pytestmark = pytest.mark.asyncio


async def _seed_store(session, *, store_id: int = 8501) -> None:
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
    await session.commit()


async def _seed_credential(session, *, store_id: int = 8501, expired: bool = False) -> None:
    now = datetime.now(timezone.utc)
    await _seed_store(session, store_id=store_id)
    session.add(
        StorePlatformCredential(
            store_id=store_id,
            platform="taobao",
            credential_type="oauth",
            access_token="taobao-session-token",
            refresh_token="taobao-refresh-token",
            expires_at=now - timedelta(minutes=5) if expired else now + timedelta(days=1),
            scope="taobao.trades.sold.get,taobao.trade.fullinfo.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="taobao_user_id",
            granted_identity_value=f"tb-user-{store_id}",
            granted_identity_display=f"tb-shop-{store_id}",
        )
    )
    await session.commit()


def _config() -> TaobaoTopConfig:
    return TaobaoTopConfig(
        app_key="taobao-app-key",
        app_secret="taobao-app-secret",
        api_base_url="https://eco.taobao.com/router/rest",
        sign_method="md5",
    )


async def test_check_pull_ready_returns_credential_missing_when_no_credential(session):
    await _clear_taobao_state(session)
    await _seed_store(session, store_id=8501)

    service = TaobaoPullService(session, config=_config())
    store_id = 8501
    result = await service.check_pull_ready(store_id=store_id)

    assert result.store_id == store_id
    assert result.platform == "taobao"
    assert result.executed_real_pull is False
    assert result.pull_ready is False
    assert result.status == "auth_pending"
    assert result.status_reason == "credential_missing"


async def test_check_pull_ready_returns_real_pull_disabled_when_not_allowed(session):
    await _clear_taobao_state(session)
    await _seed_credential(session, store_id=8502)

    service = TaobaoPullService(session, config=_config())
    result = await service.check_pull_ready(store_id=8502, allow_real_request=False)

    assert result.store_id == 8502
    assert result.executed_real_pull is False
    assert result.pull_ready is False
    assert result.status == "error"
    assert result.status_reason == "real_pull_disabled"


async def test_check_pull_ready_returns_real_pull_ok_when_summary_and_detail_loaded(session, monkeypatch):
    await _clear_taobao_state(session)
    await _seed_credential(session, store_id=8503)

    async def _fake_fetch_order_page(self, *, session, params):
        assert params.store_id == 8503
        assert params.start_time == "2026-03-29 00:00:00"
        assert params.end_time == "2026-03-29 23:59:59"
        assert params.status == "WAIT_SELLER_SEND_GOODS"
        assert params.page == 2
        assert params.page_size == 50

        return TaobaoOrderPageResult(
            page=2,
            page_size=50,
            orders_count=1,
            has_more=False,
            start_time="2026-03-28 23:59:00",
            end_time="2026-03-29 23:59:59",
            orders=[
                TaobaoOrderSummary(
                    tid="TB-PULL-8503",
                    status="WAIT_SELLER_SEND_GOODS",
                    type="fixed",
                    created="2026-03-29 12:00:00",
                    pay_time="2026-03-29 12:05:00",
                    modified="2026-03-29 12:10:00",
                    receiver_name="张三",
                    receiver_mobile="13800138000",
                    receiver_address="测试路 1 号",
                    payment="99.00",
                    total_fee="109.00",
                    items_count=1,
                    raw_order={},
                )
            ],
            raw_payload={},
        )

    async def _fake_fetch_order_detail(self, *, session, store_id: int, tid: str):
        assert store_id == 8503
        assert tid == "TB-PULL-8503"

        return TaobaoOrderDetail(
            tid="TB-PULL-8503",
            status="WAIT_SELLER_SEND_GOODS",
            type="fixed",
            buyer_nick="buyer-demo",
            buyer_open_uid="ou-demo",
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
                    oid="TB-OID-8503",
                    num_iid="NUMIID8503",
                    sku_id="SKUID8503",
                    outer_iid="OUTER-ITEM-8503",
                    outer_sku_id="OUTER-SKU-8503",
                    title="淘宝测试商品",
                    price="99.00",
                    num=1,
                    payment="99.00",
                    total_fee="99.00",
                    sku_properties_name="颜色:黑色",
                    raw_item={},
                )
            ],
            raw_payload={},
        )

    monkeypatch.setattr(
        taobao_pull_module.TaobaoRealPullService,
        "fetch_order_page",
        _fake_fetch_order_page,
    )
    monkeypatch.setattr(
        taobao_pull_module.TaobaoOrderDetailService,
        "fetch_order_detail",
        _fake_fetch_order_detail,
    )

    service = TaobaoPullService(session, config=_config())
    result = await service.check_pull_ready(
        store_id=8503,
        allow_real_request=True,
        start_time="2026-03-29 00:00:00",
        end_time="2026-03-29 23:59:59",
        status="WAIT_SELLER_SEND_GOODS",
        page=2,
        page_size=50,
    )

    assert result.store_id == 8503
    assert result.executed_real_pull is True
    assert result.pull_ready is True
    assert result.status == "ready"
    assert result.status_reason == "real_pull_ok"
    assert result.orders_count == 1
    assert result.detailed_orders_count == 1
    assert result.page == 2
    assert result.page_size == 50
    assert result.has_more is False
    assert result.start_time == "2026-03-28 23:59:00"
    assert result.end_time == "2026-03-29 23:59:59"
    assert len(result.orders) == 1
    assert result.orders[0].tid == "TB-PULL-8503"
    assert result.orders[0].detail_loaded is True
    assert result.orders[0].detail is not None
    assert result.orders[0].detail.items is not None
    assert result.orders[0].detail.items[0].outer_sku_id == "OUTER-SKU-8503"


async def test_check_pull_ready_returns_real_pull_failed_when_pull_errors(session, monkeypatch):
    await _clear_taobao_state(session)
    await _seed_credential(session, store_id=8504)

    async def _fake_fetch_order_page(self, *, session, params):
        raise TaobaoRealPullServiceError("boom")

    monkeypatch.setattr(
        taobao_pull_module.TaobaoRealPullService,
        "fetch_order_page",
        _fake_fetch_order_page,
    )

    service = TaobaoPullService(session, config=_config())
    result = await service.check_pull_ready(
        store_id=8504,
        allow_real_request=True,
        start_time="2026-03-29 00:00:00",
        end_time="2026-03-29 23:59:59",
    )

    assert result.store_id == 8504
    assert result.executed_real_pull is True
    assert result.pull_ready is False
    assert result.status == "error"
    assert result.status_reason == "real_pull_failed"
    assert result.orders_count == 0
    assert result.orders == []
