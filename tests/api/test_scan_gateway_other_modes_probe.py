import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


@pytest.mark.asyncio
async def test_other_modes_probe_event_log(session):
    """
    将 receive / putaway / count 三个 probe 冒烟放在同一事件循环里串行执行，
    避免 httpx / asyncpg 在参数化用例间切换事件循环导致的 close/ping 冲突。
    """
    from app.main import app

    modes = ["receive", "putaway", "count"]

    # 使用 ASGITransport（不传 lifespan，兼容你当前 httpx 版本）
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for mode in modes:
            payload = {
                "mode": mode,
                "tokens": {"barcode": "LOC:1"},
                "ctx": {"device_id": "RF01"},
                "probe": True,
            }
            resp = await client.post("/scan", json=payload)
            assert resp.status_code == 200, resp.text

            data = resp.json()
            assert data["committed"] is False
            ev_id = data["event_id"]

            # 事件已入库，source=scan_<mode>_probe
            src = (
                await session.execute(
                    text("SELECT source FROM event_log WHERE id=:id"),
                    {"id": ev_id},
                )
            ).scalar_one()
            assert src == f"scan_{mode}_probe"
