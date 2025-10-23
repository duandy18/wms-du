import pytest
from sqlalchemy import text
from app.db.session import async_session_maker
from app.services.event_gateway import enforce_transition

pytestmark = pytest.mark.asyncio

async def _snap(p, s, o):
    async with async_session_maker() as sess:
        row = (await sess.execute(
            text("""SELECT state FROM order_state_snapshot
                    WHERE platform=:p AND shop_id=:s AND order_no=:o"""),
            {"p": p, "s": s, "o": o},
        )).first()
        return row[0] if row else None

async def test_snapshot_allows_flow_without_from_state():
    p, s, o = "tmall", "shop-1", "SNAP-QUICK-1"
    async with async_session_maker() as sess:
        # None -> PAID（不带 from_state）
        await enforce_transition(sess, platform=p, shop_id=s, order_no=o,
                                 idem_key="K1", from_state=None, to_state="PAID", payload={})
        await sess.commit()
        assert await _snap(p, s, o) == "PAID"
        # PAID -> ALLOCATED（仍不带 from_state）
        await enforce_transition(sess, platform=p, shop_id=s, order_no=o,
                                 idem_key="K2", from_state=None, to_state="ALLOCATED", payload={})
        await sess.commit()
        assert await _snap(p, s, o) == "ALLOCATED"
