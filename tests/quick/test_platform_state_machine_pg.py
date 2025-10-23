# tests/quick/test_platform_state_machine_pg.py
import asyncio
import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import async_session_maker
from app.services.event_gateway import enforce_transition
from app.domain.events_enums import EventState

pytestmark = pytest.mark.asyncio

async def _count_illegal(session: AsyncSession, order_no: str) -> int:
    row = await session.execute(
        text("SELECT COUNT(*) FROM event_error_log WHERE order_no = :o AND error_code='ILLEGAL_TRANSITION'"),
        {"o": order_no},
    )
    return int(row.scalar() or 0)

async def _new_session() -> AsyncSession:
    return await async_session_maker().__aenter__()

async def test_legal_transitions_no_error():
    async with await _new_session() as s:
        # None -> PAID -> ALLOCATED -> SHIPPED are legal
        await enforce_transition(s, platform="tmall", shop_id="shop-1",
                                 order_no="ORD-Q1", idem_key="Q1-1",
                                 from_state=None, to_state=EventState.PAID.value, payload={"k": "v"})
        await enforce_transition(s, platform="tmall", shop_id="shop-1",
                                 order_no="ORD-Q1", idem_key="Q1-2",
                                 from_state=EventState.PAID.value, to_state=EventState.ALLOCATED.value, payload={})
        await enforce_transition(s, platform="tmall", shop_id="shop-1",
                                 order_no="ORD-Q1", idem_key="Q1-3",
                                 from_state=EventState.ALLOCATED.value, to_state=EventState.SHIPPED.value, payload={})
        await s.commit()
        assert await _count_illegal(s, "ORD-Q1") == 0

async def test_illegal_backward_transition_is_logged():
    async with await _new_session() as s:
        before = await _count_illegal(s, "ORD-Q2")
        with pytest.raises(ValueError):
            await enforce_transition(s, platform="tmall", shop_id="shop-1",
                                     order_no="ORD-Q2", idem_key="Q2-1",
                                     from_state=EventState.ALLOCATED.value, to_state=EventState.PAID.value,
                                     payload={"demo": True})
        await s.commit()
        after = await _count_illegal(s, "ORD-Q2")
        assert after == before + 1
