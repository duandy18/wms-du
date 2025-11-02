import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


@pytest.mark.asyncio
async def test_scan_pick_probe_event_log(session):
    from app.main import app  # 确保 /scan 已挂载（scan.py 采用延迟导入，不依赖 PickService）

    payload = {
        "mode": "pick",
        "tokens": {"barcode": "TASK:42 LOC:1 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": True,
    }

    # httpx >= 0.28: 使用 ASGITransport 适配 FastAPI 应用
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/scan", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["committed"] is False
    assert data["scan_ref"].startswith("scan:")
    ev_id = data["event_id"]

    # 事件已入库
    row = (
        await session.execute(
            text("SELECT id, source, message FROM event_log WHERE id=:id"),
            {"id": ev_id},
        )
    ).first()
    assert row is not None
    assert row[1] == "scan_pick_probe"
    assert row[2] == data["scan_ref"]

    # 视图可复盘（至少 e 侧≥1 行；提交腿才会出现台账腿）
    n = (
        await session.execute(
            text("SELECT COUNT(*) FROM v_scan_trace WHERE scan_ref=:r"),
            {"r": data["scan_ref"]},
        )
    ).scalar_one()
    assert n >= 1
