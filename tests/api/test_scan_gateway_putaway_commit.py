import httpx
import pytest
from sqlalchemy import text

async def _has_col(session, table: str, col: str) -> bool:
    sql = text("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
         LIMIT 1
    """)
    return (await session.execute(sql, {"t": table, "c": col})).first() is not None

@pytest.mark.asyncio
async def test_scan_putaway_commit_moves_stock_two_legs(session):
    # 主数据
    await session.execute(text("INSERT INTO warehouses(id,name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO locations(id,name,warehouse_id) VALUES (1,'DST',1) ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO locations(id,name,warehouse_id) VALUES (900,'SRC',1) ON CONFLICT (id) DO NOTHING"))

    # items 自适应列
    has_sku = await _has_col(session, "items", "sku")
    has_uom = await _has_col(session, "items", "uom")

    cols = ["id", "name"]
    vals = ["3001", "'ITEM'"]
    upd = ["name=EXCLUDED.name"]
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
        ON CONFLICT (id) DO UPDATE SET {", ".join(upd)}
    """))

    # 源位库存 +5（含 batch_code）
    await session.execute(
        text("INSERT INTO stocks(item_id,warehouse_id,location_id,batch_code,qty) VALUES (3001,1,900,'B-900',5)")
    )
    await session.commit()

    from app.main import app
    payload = {
        "mode": "putaway",
        "tokens": {"barcode": "LOC:1 ITEM:3001 QTY:2"},
        "from_location_id": 900,
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/scan", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["committed"] is True and data["source"] == "scan_putaway_commit"

    # A→B 双腿（PUTAWAY 正负成对）
    legs = (
        await session.execute(
            text("SELECT reason, delta, location_id FROM stock_ledger WHERE ref=:ref ORDER BY id"),
            {"ref": data["scan_ref"]},
        )
    ).all()
    assert any(l[0] == "PUTAWAY" and l[1] < 0 and l[2] == 900 for l in legs)
    assert any(l[0] == "PUTAWAY" and l[1] > 0 and l[2] == 1 for l in legs)
