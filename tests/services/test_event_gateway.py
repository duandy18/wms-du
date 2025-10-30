import pytest

pytestmark = pytest.mark.grp_events

import pytest

pytestmark = pytest.mark.asyncio


async def test_publish_once_and_dedupe(monkeypatch, session):
    from app.services.event_gateway import EventGateway

    calls = {"n": 0}

    async def _fake_emit(topic, data):
        calls["n"] += 1
        return True

    gw = EventGateway()
    monkeypatch.setattr(gw, "_emit", _fake_emit)

    event_id = "EVT-001"
    payload = {"type": "StockAdjusted", "delta": 5}
    await gw.publish(session=session, event_id=event_id, payload=payload)
    await gw.publish(session=session, event_id=event_id, payload=payload)  # 重放

    assert calls["n"] == 1
