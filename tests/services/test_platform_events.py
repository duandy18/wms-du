import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.xfail(reason="WIP: event publish/consume", strict=False)]

async def test_publish_consume_idempotent(session, _baseline_seed, _db_clean):
    from app.services.platform_events import PlatformEvents
    ev = PlatformEvents()
    eid1 = await ev.publish(session=session, topic="inventory.synced", payload={"item_id": 1})
    eid2 = await ev.publish(session=session, topic="inventory.synced", payload={"item_id": 1})
    assert eid1 == eid2  # 幂等期望（若实现不同，后续调整）
