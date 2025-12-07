# Path: tests/services/phase34/test_ship_replay_concurrency.py
import asyncio
import random
import string
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

ITEM_ID = 3003
WH_ID = 1
BASE_QTY = 10
PARALLEL = 32

PLATFORM = "pdd"
SHOP_ID = "1"  # 接口要求字符串


def _rand_ref(prefix="SHIP-P34"):
    suff = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}:{suff}"


@pytest_asyncio.fixture
async def client_like(request):
    for name in ("async_client", "client", "http_client", "app_client"):
        try:
            cli = request.getfixturevalue(name)
            yield cli
            return
        except Exception:
            continue
    import httpx

    from app.main import app  # 按你的导出路径

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def db_session_like(request):
    for name in ("async_session", "session"):
        try:
            return request.getfixturevalue(name)
        except Exception:
            continue
    pytest.fail("缺少数据库会话 fixture（async_session/session）。")


@pytest_asyncio.fixture
async def ship_path():
    yield "/outbound/ship/commit"


async def _assert_baseline_ready(session):
    r = await session.execute(
        text("SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND warehouse_id=:w"),
        {"i": ITEM_ID, "w": WH_ID},
    )
    qty = int(r.scalar() or 0)
    if qty < BASE_QTY:
        pytest.fail(
            f"Phase 3.4 基线未就绪：stocks(sum)={qty}，应≥{BASE_QTY}；先执行 alembic upgrade head"
        )


async def _read_sum(session):
    r = await session.execute(
        text("SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND warehouse_id=:w"),
        {"i": ITEM_ID, "w": WH_ID},
    )
    return int(r.scalar() or 0)


async def _count_ship_ledger(session, ref_prefix):
    r = await session.execute(
        text("SELECT COUNT(*) FROM ledger WHERE ref LIKE :pfx || '%' AND delta < 0"),
        {"pfx": ref_prefix},
    )
    return int(r.scalar() or 0)


@pytest.mark.asyncio
async def test_ship_replay_idempotency(client_like, db_session_like, ship_path):
    await _assert_baseline_ready(db_session_like)

    # 直发出库：不要求已有 RESERVE；服务内 FEFO 扣减
    ref = _rand_ref()
    payload = {
        "ref": ref,
        "platform": PLATFORM,
        "shop_id": SHOP_ID,
        "warehouse_id": WH_ID,
        "lines": [{"item_id": ITEM_ID, "qty": 7}],
        "ts": datetime.now(UTC).isoformat(),
    }

    # 先单发一次确保契约 OK
    p = await client_like.post(ship_path, json=payload)
    assert p.status_code in (
        200,
        201,
        202,
        204,
        206,
        409,
    ), f"SHIP 契约/业务不通过: {p.status_code} {p.text}"

    async def _fire_once():
        r = await client_like.post(ship_path, json=payload)
        return r.status_code

    codes = await asyncio.gather(*(_fire_once() for _ in range(PARALLEL)))

    # 扣 7 一次，幂等重放不再扣
    after = await _read_sum(db_session_like)
    assert after == BASE_QTY - 7, f"stocks.sum expect {BASE_QTY - 7}, got {after}, codes={codes}"

    cnt = await _count_ship_ledger(db_session_like, ref_prefix=ref)
    assert cnt <= 1, f"ledger negatives for same ref should be <=1, got {cnt}, codes={codes}"
