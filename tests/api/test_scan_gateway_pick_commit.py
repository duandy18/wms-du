import sys
import types

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


@pytest.mark.asyncio
async def test_scan_pick_commit_event_log(session, monkeypatch):
    # 1) 准备：把 app.services.pick_service 注入一个假的模块（延迟导入时会用它）
    fake_mod = types.ModuleType("app.services.pick_service")

    class PickService:  # noqa: N801 (匹配真实类名)
        async def record_pick(
            self,
            session,
            task_line_id: int,
            from_location_id: int,
            item_id: int,
            qty: int,
            scan_ref: str,
            operator=None,
        ):
            # 不做真实扣库，直接返回一个可预测结果
            return {
                "task_id": 42,
                "task_line_id": task_line_id or 42,
                "picked": qty,
                "remain": 0,
                "from_location_id": from_location_id,
                "item_id": item_id,
                "ref": scan_ref,
                "operator": operator,
            }

    setattr(fake_mod, "PickService", PickService)
    sys.modules["app.services.pick_service"] = fake_mod

    # 2) 起应用并请求 /scan（commit 路径）
    from app.main import app  # noqa

    payload = {
        "mode": "pick",
        "tokens": {"barcode": "TASK:42 LOC:1 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
        # 可选：显式给出 task_line_id，若不给也无所谓（假服务里做兜底）
        "task_line_id": 4242,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/scan", json=payload)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["committed"] is True
    assert data["scan_ref"].startswith("scan:")
    ev_id = data["event_id"]

    # 3) 事件已入库（commit 事件）
    row = (
        await session.execute(
            text("SELECT id, source, message FROM event_log WHERE id=:id"),
            {"id": ev_id},
        )
    ).first()
    assert row is not None
    assert row[1] == "scan_pick_commit"
    assert row[2] == data["scan_ref"]

    # 4) v_scan_trace 可复盘该 scan_ref（至少 e 侧≥1；真实台账腿以后接入）
    n = (
        await session.execute(
            text("SELECT COUNT(*) FROM v_scan_trace WHERE scan_ref=:r"),
            {"r": data["scan_ref"]},
        )
    ).scalar_one()
    assert n >= 1
