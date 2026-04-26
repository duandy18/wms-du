from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.oms.platforms.models.jd_app_config import JdAppConfig
from app.oms.platforms.models.store_platform_credential import StorePlatformCredential
from app.oms.platforms.jd import service_pull as jd_pull_module
from app.oms.platforms.jd.service_order_detail import (
    JdOrderDetail,
    JdOrderDetailItem,
)
from app.oms.platforms.jd.service_pull import JdPullService
from app.oms.platforms.jd.service_real_pull import (
    JdOrderPageResult,
    JdOrderSummary,
)


def _jd_app_config(
    *,
    row_id: int = 1,
    client_id: str = "jd-client-id-001",
    client_secret: str = "jd-client-secret-001",
    callback_url: str = "http://127.0.0.1:8000/oms/jd/oauth/callback",
    gateway_url: str = "https://api.jd.com/routerjson",
    sign_method: str = "md5",
    is_enabled: bool = True,
) -> JdAppConfig:
    now = datetime.now(timezone.utc)
    return JdAppConfig(
        id=row_id,
        client_id=client_id,
        client_secret=client_secret,
        callback_url=callback_url,
        gateway_url=gateway_url,
        sign_method=sign_method,
        is_enabled=is_enabled,
        created_at=now,
        updated_at=now,
    )


def _store_row_sql(store_id: int) -> str:
    return f"""
    INSERT INTO stores (
  id,
  platform,
  store_code,
  store_name,
  active
)
VALUES (
  {store_id},
  'jd',
  'store-{store_id}',
  'store-{store_id}',
  true
)
    ON CONFLICT (id) DO NOTHING
    """


async def _clear_jd_state(session) -> None:
    await session.execute(text("DELETE FROM store_platform_connections WHERE platform = 'jd'"))
    await session.execute(text("DELETE FROM store_platform_credentials WHERE platform = 'jd'"))
    await session.execute(text("DELETE FROM jd_app_configs"))
    await session.commit()


@pytest.mark.asyncio
async def test_check_pull_ready_returns_platform_app_not_ready_when_missing(session):
    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(801)))
    await session.commit()

    service = JdPullService()
    result = await service.check_pull_ready(session=session, store_id=801)
    await session.commit()

    assert result.platform == "jd"
    assert result.store_id == 801
    assert result.status == "not_ready"
    assert result.status_reason == "platform_app_not_ready"
    assert result.connection_status == "not_connected"
    assert result.credential_status == "missing"
    assert result.reauth_required is False
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_credential_missing_when_no_credential(session):
    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(802)))
    session.add(_jd_app_config(row_id=1001))
    await session.commit()

    service = JdPullService()
    result = await service.check_pull_ready(session=session, store_id=802)
    await session.commit()

    assert result.platform == "jd"
    assert result.store_id == 802
    assert result.status == "not_ready"
    assert result.status_reason == "credential_missing"
    assert result.connection_status == "not_connected"
    assert result.credential_status == "missing"
    assert result.reauth_required is False
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_credential_expired_when_token_expired(session):
    now = datetime.now(timezone.utc)

    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(803)))
    session.add(_jd_app_config(row_id=1002))
    session.add(
        StorePlatformCredential(
            store_id=803,
            platform="jd",
            credential_type="oauth",
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=now - timedelta(minutes=5),
            scope="jingdong.pop.order.search",
            raw_payload_json={"source": "test"},
            granted_identity_type="jd_uid",
            granted_identity_value="uid-803",
            granted_identity_display="store-803",
        )
    )
    await session.commit()

    service = JdPullService()
    result = await service.check_pull_ready(session=session, store_id=803)
    await session.commit()

    assert result.platform == "jd"
    assert result.store_id == 803
    assert result.status == "not_ready"
    assert result.status_reason == "credential_expired"
    assert result.connection_status == "connected"
    assert result.credential_status == "expired"
    assert result.reauth_required is True
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_real_pull_ok_when_summary_and_detail_loaded(session, monkeypatch):
    now = datetime.now(timezone.utc)

    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(804)))
    session.add(_jd_app_config(row_id=1003))
    session.add(
        StorePlatformCredential(
            store_id=804,
            platform="jd",
            credential_type="oauth",
            access_token="valid-token",
            refresh_token="refresh-token",
            expires_at=now + timedelta(days=1),
            scope="jingdong.pop.order.search,jingdong.pop.order.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="jd_uid",
            granted_identity_value="uid-804",
            granted_identity_display="store-804",
        )
    )
    await session.commit()

    async def _fake_fetch_order_page(self, *, session, params):
        assert params.store_id == 804
        return JdOrderPageResult(
            page=1,
            page_size=20,
            orders_count=1,
            has_more=False,
            start_time="2026-03-29 00:00:00",
            end_time="2026-03-29 23:59:59",
            orders=[
                JdOrderSummary(
                    platform_order_id="JD-ORDER-804",
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
                    raw_order={},
                )
            ],
            raw_payload={},
        )

    async def _fake_fetch_order_detail(self, *, session, store_id: int, order_id: str):
        assert store_id == 804
        assert order_id == "JD-ORDER-804"
        return JdOrderDetail(
            order_id="JD-ORDER-804",
            vender_id="VENDER-804",
            order_type="SOP",
            order_state="WAIT_SELLER_STOCK_OUT",
            buyer_pin="buyer-804",
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
                    sku_id="SKU-JD-804",
                    outer_sku_id="OUTER-SKU-804",
                    ware_id="WARE-804",
                    item_name="京东测试商品A",
                    item_total=2,
                    item_price="39.90",
                    sku_name="颜色:黑;尺码:M",
                    gift_point=0,
                    raw_item={},
                )
            ],
            raw_payload={},
        )

    monkeypatch.setattr(
        jd_pull_module.JdRealPullService,
        "fetch_order_page",
        _fake_fetch_order_page,
    )
    monkeypatch.setattr(
        jd_pull_module.JdOrderDetailService,
        "fetch_order_detail",
        _fake_fetch_order_detail,
    )

    service = JdPullService()
    result = await service.check_pull_ready(session=session, store_id=804)
    await session.commit()

    assert result.platform == "jd"
    assert result.store_id == 804
    assert result.status == "ready"
    assert result.status_reason == "real_pull_ok"
    assert result.connection_status == "connected"
    assert result.credential_status == "valid"
    assert result.reauth_required is False
    assert result.pull_ready is True
    assert result.orders_count == 1
    assert result.detailed_orders_count == 1
    assert len(result.orders) == 1
    assert result.orders[0].platform_order_id == "JD-ORDER-804"
    assert result.orders[0].detail_loaded is True
    assert result.orders[0].detail is not None


@pytest.mark.asyncio
async def test_check_pull_ready_persists_connection_row(session):
    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(805)))
    await session.commit()

    service = JdPullService()
    await service.check_pull_ready(session=session, store_id=805)
    await session.commit()

    stmt = text(
        """
        SELECT id, platform
        FROM store_platform_connections
        WHERE store_id = :store_id AND platform = 'jd'
        LIMIT 1
        """
    )
    result = await session.execute(stmt, {"store_id": 805})
    row = result.first()

    assert row is not None
    assert row.platform == "jd"
