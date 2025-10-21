import pytest
from app.services.platform_events import handle_event_batch

@pytest.mark.asyncio
async def test_handle_pdd_event_batch():
    events = [
        {"platform": "pdd", "order_sn": "P12345", "status": "PAID"},
        {"platform": "pdd", "order_sn": "P99999", "status": "CANCEL"},
    ]
    await handle_event_batch(events)
    assert True

@pytest.mark.asyncio
async def test_handle_taobao_event_batch():
    events = [
        {"platform": "taobao", "tid": "T123", "trade_status": "WAIT_SELLER_SEND_GOODS"},
        {"platform": "taobao", "tid": "T999", "trade_status": "TRADE_CLOSED"},
    ]
    await handle_event_batch(events)
    assert True

@pytest.mark.asyncio
async def test_handle_jd_event_batch():
    events = [
        {"platform": "jd", "orderId": "J123", "orderStatus": "PAID"},
        {"platform": "jd", "orderId": "J999", "orderStatus": "CANCEL"},
    ]
    await handle_event_batch(events)
    assert True
