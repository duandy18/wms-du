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
async def test_scan_receive_commit_creates_ledger(session):
    # 基线主数据
    await session.execute(text("INSERT INTO warehouses(id,name) VALUES (1,'WH') ON CONFLICT (id) DO NOTHING"))
    await session.execute(text("INSERT INTO locations(id,name,warehouse_id) VALUES (1,'LOC-1',1) ON CONFLICT (id) DO NOTHING"))

    # items 自适应：若存在 sku/uom（或为 NOT NULL），则一并写入
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
    await session.commit()

    # 走 /scan receive commit（真动作）
    from app.main import app
    payload = {
        "mode": "receive",
        "tokens": {"barcode": "LOC:1 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": False,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/scan", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["committed"] is True and data["source"] == "scan_receive_commit"

    # 至少有一条 INBOUND 正腿台账
    rows = (
        await session.execute(
            text("SELECT reason, delta FROM stock_ledger WHERE ref=:ref ORDER BY id"),
            {"ref": data["scan_ref"]},
        )
    ).all()
    assert any(rr[0] == "INBOUND" and rr[1] > 0 for rr in rows)
