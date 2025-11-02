import httpx
import pytest
from sqlalchemy import text
from asyncio import sleep

# 自适应检测表字段的小工具：有些环境 items 带 sku/uom，必须同时写入
async def _has_col(session, table: str, col: str) -> bool:
    sql = text("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = :t
           AND column_name = :c
         LIMIT 1
    """)
    return (await session.execute(sql, {"t": table, "c": col})).first() is not None


@pytest.mark.asyncio
async def test_event_to_ledger_appears_within_2s(session):
    # 0) 准备一条可扣减库存（便于走 commit）
    await session.execute(
        text("INSERT INTO warehouses(id,name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING")
    )
    await session.execute(
        text("INSERT INTO locations(id,name,warehouse_id) VALUES (1,'LOC',1) ON CONFLICT (id) DO NOTHING")
    )

    # items 表：若存在 sku/uom（或为 NOT NULL），则一并写入，避免约束报错
    has_sku = await _has_col(session, "items", "sku")
    has_uom = await _has_col(session, "items", "uom")

    cols = ["id", "name"]
    vals = ["3001", "'ITEM'"]
    upd  = ["name=EXCLUDED.name"]

    if has_sku:
        cols.insert(1, "sku")
        vals.insert(1, "'SKU-3001'")
        upd.insert(0, "sku=EXCLUDED.sku")
    if has_uom:
        cols.append("uom")
        vals.append("'PCS'")
        upd.append("uom=COALESCE(items.uom, EXCLUDED.uom)")

    await session.execute(text(f"""
        INSERT INTO items ({", ".join(cols)})
        VALUES ({", ".join(vals)})
        ON CONFLICT (id) DO UPDATE
          SET {", ".join(upd)}
    """))

    # 账面 5
    await session.execute(
        text("INSERT INTO stocks(item_id,warehouse_id,location_id,batch_code,qty) VALUES (3001,1,1,'B-1',5)")
    )
    await session.commit()

    # 1) 走 /scan commit（count：实盘 3 → 账面 5，生成 -2 差额腿）
    from app.main import app
    payload = {
        "mode": "count",
        "tokens": {"barcode": "LOC:1 ITEM:3001 QTY:3"},  # ★ 必然产生台账腿
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/scan", json=payload)
    assert r.status_code == 200, r.text
    ref = r.json()["scan_ref"]

    # 2) 轮询 v_scan_trace ≤2s 命中至少 1 条台账腿
    found = False
    for _ in range(10):  # 10 * 0.2s = 2s
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

    assert found, f"no ledger legs appear for {ref} within 2s"
