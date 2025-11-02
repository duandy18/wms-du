import httpx
import pytest
from sqlalchemy import text
from asyncio import sleep

@pytest.mark.asyncio
async def test_event_to_ledger_appears_within_1s(session):
    # 准备一条可扣减库存（便于走 commit）
    await session.execute(text("INSERT INTO warehouses(id,name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO locations(id,name,warehouse_id) VALUES (1,'LOC',1) ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO items(id,name) VALUES (3001,'ITEM') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO stocks(item_id,warehouse_id,location_id,batch_code,qty) VALUES (3001,1,1,'B-1',5)"))
    await session.commit()

    from app.main import app
    payload = {
        "mode": "count",  # 选最轻路径；也可替换为 receive/putaway/pick
        "tokens": {"barcode": "LOC:1 ITEM:3001 QTY:5"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/scan", json=payload)
    assert r.status_code == 200, r.text
    ref = r.json()["scan_ref"]

    # 轮询 v_scan_trace ≤1s 命中至少 1 条台账腿
    found = False
    for _ in range(5):
        rows = (
            await session.execute(
                text("SELECT ledger_id FROM v_scan_trace WHERE scan_ref=:r AND ledger_id IS NOT NULL"),
                {"r": ref},
            )
        ).all()
        if rows:
            found = True
            break
        await sleep(0.2)
    assert found, f"no ledger legs appear for {ref} within 1s"
