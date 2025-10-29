import pytest

pytestmark = pytest.mark.asyncio

async def test_consume_idempotent(session):
    from app.services.process_event import ProcessEvent
    pe = ProcessEvent()

    payload = {"event":"ORDER_PAID","order_no":"PE-1001"}
    r1 = await pe.consume(session=session, payload=payload)
    r2 = await pe.consume(session=session, payload=payload)  # 重放

    assert r1.get("accepted") is True
    assert r2.get("idempotent") is True
