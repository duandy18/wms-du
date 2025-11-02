import pytest
from sqlalchemy import text
from app.services.pick_service import PickService

pytestmark = pytest.mark.grp_scan

class _NoOpStock:
    async def adjust(self, **kwargs):  # 不触发真实扣库
        return

@pytest.mark.asyncio
async def test_pick_by_context_selects_line_and_updates_status(session):
    # 建任务头与两行
    tid = (await session.execute(text("INSERT INTO pick_tasks (warehouse_id, ref, assigned_to) VALUES (1, 'T-CTX', 'RF01') RETURNING id"))).scalar_one()
    l1 = (await session.execute(text("INSERT INTO pick_task_lines (task_id, item_id, req_qty) VALUES (:t, 3001, 3) RETURNING id"), {"t": tid})).scalar_one()
    l2 = (await session.execute(text("INSERT INTO pick_task_lines (task_id, item_id, req_qty) VALUES (:t, 3002, 2) RETURNING id"), {"t": tid})).scalar_one()

    svc = PickService(_NoOpStock())
    # RF01 合法；RF02 应拒绝
    with pytest.raises(PermissionError):
        await svc.record_pick_by_context(session, tid, item_id=3001, qty=1, scan_ref="scan:ctx", device_id="RF02")

    r = await svc.record_pick_by_context(session, tid, item_id=3001, qty=1, scan_ref="scan:ctx", device_id="RF01")
    assert r["task_id"] == tid and r["picked"] == 1 and r["remain"] == 2

    st = (await session.execute(text("SELECT status FROM pick_task_lines WHERE id=:id"), {"id": l1})).scalar_one()
    assert st in ("OPEN","PARTIAL")  # 1/3
