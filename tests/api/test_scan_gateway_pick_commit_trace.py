import uuid

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


async def _has_col(session, table: str, col: str) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema='public'
                   AND table_name=:t
                   AND column_name=:c
                """
            ),
            {"t": table, "c": col},
        )
    ).first()
    return row is not None


@pytest.mark.asyncio
async def test_scan_pick_commit_generates_ledger_and_trace(session):
    # 0) 最小主数据（幂等 UPSERT）
    await session.execute(
        text(
            """
        INSERT INTO warehouses (id, name)
        VALUES (1, 'WH1')
        ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """
        )
    )
    await session.execute(
        text(
            """
        INSERT INTO locations (id, name, warehouse_id)
        VALUES (1, 'LOC-1', 1)
        ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, warehouse_id=EXCLUDED.warehouse_id
        """
        )
    )

    # 0.1) 自适应 items 列：至少保证 id、name；有 sku/uom 就一并处理
    has_sku = await _has_col(session, "items", "sku")
    has_uom = await _has_col(session, "items", "uom")

    cols = ["id", "name"]
    vals = ["3001", "'TEST-ITEM'"]
    upd_sets = ["name=EXCLUDED.name"]

    if has_sku:
        cols.insert(1, "sku")
        vals.insert(1, "'SKU-3001'")
        upd_sets.insert(0, "sku=EXCLUDED.sku")
    if has_uom:
        cols.append("uom")
        vals.append("'PCS'")
        upd_sets.append("uom=COALESCE(items.uom, EXCLUDED.uom)")

    sql_items = f"""
        INSERT INTO items ({", ".join(cols)})
        VALUES ({", ".join(vals)})
        ON CONFLICT (id) DO UPDATE
          SET {", ".join(upd_sets)}
    """
    await session.execute(text(sql_items))
    # 提交主数据，确保 /scan 的独立会话可见
    await session.commit()

    # 1) 预置现货：真实扣库需要有货可减（+5）
    from app.services.stock_service import StockService

    stock = StockService()
    await stock.adjust(
        session=session,
        item_id=3001,
        location_id=1,
        delta=+5,
        reason="SEED",
        ref="seed:stock",
    )
    # 提交种子库存
    await session.commit()

    # 2) 生成任务（req=2），设备绑定 RF01；ref 使用唯一后缀防止多次运行撞唯一键
    unique_ref = f"T-REAL-{uuid.uuid4().hex[:8]}"
    tid = (
        await session.execute(
            text(
                "INSERT INTO pick_tasks (warehouse_id, ref, assigned_to) "
                "VALUES (1, :ref, 'RF01') RETURNING id"
            ),
            {"ref": unique_ref},
        )
    ).scalar_one()
    _ = (
        await session.execute(
            text(
                "INSERT INTO pick_task_lines (task_id, item_id, req_qty) "
                "VALUES (:t, 3001, 2) RETURNING id"
            ),
            {"t": tid},
        )
    ).scalar_one()
    # 提交任务头与任务行
    await session.commit()

    # 3) 走 /scan commit（真实 PickService + 真实扣库）
    from app.main import app

    payload = {
        "mode": "pick",
        "tokens": {"barcode": f"TASK:{tid} LOC:1 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/scan", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    scan_ref = data["scan_ref"]

    # 4) 事件入库：应为 commit 事件
    ev_src = (
        await session.execute(
            text("SELECT source FROM event_log WHERE id=:id"),
            {"id": data["event_id"]},
        )
    ).scalar_one()
    assert ev_src == "scan_pick_commit"

    # 5) v_scan_trace：至少出现一条台账腿，且含 PICK 负数腿
    rows = (
        await session.execute(
            text(
                "SELECT ledger_id, reason, delta FROM v_scan_trace WHERE scan_ref=:r ORDER BY ledger_id"
            ),
            {"r": scan_ref},
        )
    ).all()
    assert any(r[0] is not None for r in rows), f"no ledger legs found for {scan_ref}"
    assert any((r[0] is not None and r[1] == "PICK" and r[2] < 0) for r in rows)

    # 6) 回放接口：前端可直接用
    transport2 = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client:
        resp2 = await client.get(f"/scan/trace/{scan_ref}")
    assert resp2.status_code == 200
    trace = resp2.json()
    assert isinstance(trace, list) and len(trace) >= 1
