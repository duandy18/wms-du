# tests/quick/test_outbound_http_pg.py
import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session  # 依赖注入口
from app.main import app

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, i: int, loc: int, q: int):
    await session.execute(
        text(
            """
          INSERT INTO stocks(item_id, location_id, qty)
          VALUES (:i,:l,:q)
          ON CONFLICT (item_id, location_id) DO UPDATE SET qty=:q
        """
        ),
        dict(i=i, l=loc, q=q),
    )


@pytest.fixture(autouse=True)
def _override_session_dep(session: AsyncSession):
    """
    为每个请求创建“新的 AsyncSession”，避免并发时共享同一个 session。
    仍然复用测试基座的 AsyncEngine（session.bind）。
    """
    engine = session.bind  # AsyncEngine
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async def _dep():
        async with SessionLocal() as s:
            # 路由里自己管理事务（session.begin()）
            yield s

    app.dependency_overrides[get_session] = _dep
    yield
    app.dependency_overrides.pop(get_session, None)


async def test_http_outbound_idempotent(session: AsyncSession):
    item_id, loc_id = 3, 1
    ref = f"SO-HTTP-1-{uuid4().hex[:8]}"  # 唯一 ref，避免历史幂等命中

    # 造数并提交，让新开的会话可见
    await _seed(session, item_id, loc_id, 10)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        body = {
            "ref": ref,
            "lines": [{"item_id": item_id, "location_id": loc_id, "qty": 3}],
        }
        r1 = await c.post("/outbound/commit", json=body)
        assert r1.status_code == 200, r1.text
        r2 = await c.post("/outbound/commit", json=body)
        assert r2.status_code == 200, r2.text

        js1, js2 = r1.json(), r2.json()
        assert js1["results"][0]["status"] == "OK"
        assert js2["results"][0]["status"] == "IDEMPOTENT"

        # 余额应为 7（直接用测试基座的 session 查）
        qty = (
            await session.execute(
                text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
                dict(i=item_id, l=loc_id),
            )
        ).scalar_one()
        assert qty == 7


async def test_http_outbound_concurrency_idempotent(session: AsyncSession):
    item_id, loc_id = 4, 1
    ref = f"SO-HTTP-2-{uuid4().hex[:8]}"  # 唯一 ref，避免与其他用例/上次运行冲突

    await _seed(session, item_id, loc_id, 10)
    await session.commit()  # 让新开的会话可见

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as c:
        body = {
            "ref": ref,
            "lines": [{"item_id": item_id, "location_id": loc_id, "qty": 5}],
        }
        r1, r2 = await asyncio.gather(
            c.post("/outbound/commit", json=body),
            c.post("/outbound/commit", json=body),
        )
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        statuses = {r.json()["results"][0]["status"] for r in (r1, r2)}
        assert statuses == {"OK", "IDEMPOTENT"}

        qty = (
            await session.execute(
                text("SELECT qty FROM stocks WHERE item_id=:i AND location_id=:l"),
                dict(i=item_id, l=loc_id),
            )
        ).scalar_one()
        assert qty == 5
