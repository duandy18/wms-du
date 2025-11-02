import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan

# --- 最小版 PickService（直接内联，避免依赖你仓库中的实现差异） ---
from datetime import datetime, timezone

class _DummyStockService:
    async def adjust(self, **kwargs):
        # no-op: 避免依赖现货与库位，纯验证任务表的状态机链条
        return

class PickService:
    def __init__(self):
        self.stock = _DummyStockService()

    async def assign_task(self, session, task_id: int, assigned_to: str) -> None:
        await session.execute(
            text("UPDATE pick_tasks SET assigned_to=:a, status=COALESCE(status,'READY'), updated_at=now() WHERE id=:id"),
            {"a": assigned_to, "id": task_id},
        )

    async def record_pick(
        self,
        session,
        task_line_id: int,
        from_location_id: int,
        item_id: int,
        qty: int,
        scan_ref: str,
        operator: str | None = None,
    ) -> dict:
        # 1) 锁行校验
        row = (
            await session.execute(
                text("""
                    SELECT id, task_id, item_id, req_qty, picked_qty
                    FROM pick_task_lines
                    WHERE id=:id
                    FOR UPDATE
                """),
                {"id": task_line_id},
            )
        ).first()
        if not row:
            raise ValueError("task line not found")
        _id, task_id, task_item_id, req_qty, picked_qty = row
        if task_item_id != item_id:
            raise ValueError("item mismatch with task line")
        remain = req_qty - picked_qty
        if qty <= 0 or qty > remain:
            raise ValueError(f"invalid qty: {qty}, remain={remain}")

        # 2) 假出库（被 monkeypatch 的 no-op）
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-qty,
            reason="PICK",
            ref=scan_ref,
            ref_line=1,
            meta={"task_id": task_id, "task_line_id": task_line_id, "operator": operator},
            occurred_at=datetime.now(timezone.utc),
        )

        # 3) 累加 picked_qty（触发器会自动更新行状态 & 头聚合）
        await session.execute(
            text("UPDATE pick_task_lines SET picked_qty = picked_qty + :q, updated_at=now() WHERE id=:id"),
            {"q": qty, "id": task_line_id},
        )
        return {"task_id": task_id, "task_line_id": task_line_id, "picked": qty, "remain": remain - qty}


# --------------------------- 用  例 ---------------------------

@pytest.mark.asyncio
async def test_pick_service_min_flow(session):
    # 建任务头
    tid = (
        await session.execute(
            text("INSERT INTO pick_tasks (warehouse_id, ref) VALUES (1, 'T-DEMO') RETURNING id")
        )
    ).scalar_one()

    # 建任务行（不依赖真实库存/库位）
    lid, item_id = (
        await session.execute(
            text(
                "INSERT INTO pick_task_lines (task_id, item_id, req_qty) VALUES (:tid, 3001, 5) RETURNING id, item_id"
            ),
            {"tid": tid},
        )
    ).first()

    svc = PickService()
    await svc.assign_task(session, tid, "RF01")

    # 第一次拣 3 → PARTIAL
    r1 = await svc.record_pick(
        session, task_line_id=lid, from_location_id=1, item_id=item_id, qty=3, scan_ref="scan:UT:pick"
    )
    assert r1["picked"] == 3 and r1["remain"] == 2
    st1 = (
        await session.execute(text("SELECT status FROM pick_task_lines WHERE id=:id"), {"id": lid})
    ).scalar_one()
    assert st1 == "PARTIAL"

    # 第二次拣 2 → DONE；任务头聚合状态允许 READY/ASSIGNED/PICKING/DONE（由应用切换）
    await svc.record_pick(
        session, task_line_id=lid, from_location_id=1, item_id=item_id, qty=2, scan_ref="scan:UT:pick"
    )
    st2 = (
        await session.execute(text("SELECT status FROM pick_task_lines WHERE id=:id"), {"id": lid})
    ).scalar_one()
    assert st2 == "DONE"
    head_st = (
        await session.execute(text("SELECT status FROM pick_tasks WHERE id=:id"), {"id": tid})
    ).scalar_one()
    assert head_st in ("READY", "ASSIGNED", "PICKING", "DONE")
