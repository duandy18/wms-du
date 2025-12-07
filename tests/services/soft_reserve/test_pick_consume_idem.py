# tests/services/soft_reserve/test_pick_consume_idem.py
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PLATFORM = "pdd"
SHOP_ID = "1"
WH_ID = 1
ITEM = 3003


@pytest.mark.asyncio
async def test_pick_consume_idempotent(client_like, db_session_like_pg: AsyncSession):
    ref = "RSV-3003-7"

    await db_session_like_pg.execute(
        text(
            "DELETE FROM reservation_lines USING reservations r WHERE reservation_id=r.id AND r.ref=:r"
        ),
        {"r": ref},
    )
    await db_session_like_pg.execute(text("DELETE FROM reservations WHERE ref=:r"), {"r": ref})
    await db_session_like_pg.commit()

    r1 = await client_like.post(
        "/reserve/persist",
        json={
            "platform": PLATFORM,
            "shop_id": SHOP_ID,
            "warehouse_id": WH_ID,
            "ref": ref,
            "lines": [{"item_id": ITEM, "qty": 7}],
        },
    )
    assert r1.status_code in (200, 201), r1.text

    payload = {"platform": PLATFORM, "shop_id": SHOP_ID, "warehouse_id": WH_ID, "ref": ref}
    sem = asyncio.Semaphore(12)

    async def _fire():
        async with sem:
            resp = await client_like.post("/reserve/pick/commit", json=payload)
            _ = resp.text
            return resp

    responses = await asyncio.gather(*(_fire() for _ in range(32)))

    ok = sum(1 for resp in responses if resp.status_code in (200, 204))
    conflicts = 0
    for resp in responses:
        if resp.status_code == 409:
            try:
                body = resp.json()
            except Exception:
                body = {}
            if (
                isinstance(body, dict)
                and body.get("detail", {}).get("code") == "reservation_not_open"
            ):
                conflicts += 1
            else:
                pytest.fail(f"unexpected 409 payload: {resp.text}")

    assert ok >= 1, f"no successful pick; statuses={[r.status_code for r in responses]}"
    assert ok + conflicts == len(
        responses
    ), f"unexpected statuses: {[(r.status_code, r.text) for r in responses]}"

    # 校验消费量与头状态
    r2 = await db_session_like_pg.execute(
        text(
            "SELECT consumed_qty FROM reservation_lines WHERE reservation_id=(SELECT id FROM reservations WHERE ref=:r)"
        ),
        {"r": ref},
    )
    assert int((r2.first() or (0,))[0] or 0) == 7

    r3 = await db_session_like_pg.execute(
        text("SELECT status FROM reservations WHERE ref=:r"), {"r": ref}
    )
    assert (r3.first() or ("",))[0].lower() == "consumed"
