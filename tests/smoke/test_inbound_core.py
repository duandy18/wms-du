from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.main import app

pytestmark = pytest.mark.smoke


async def _seed_basic(async_session_maker):
    """最小基线（幂等）"""
    async with async_session_maker() as s, s.begin():
        await s.execute(text("SET search_path TO public"))
        await s.execute(
            text(
                "INSERT INTO warehouses (id,name) VALUES (1,'WH-TEST') ON CONFLICT (id) DO NOTHING"
            )
        )
        for loc_id, loc_name in [(0, "STAGE"), (101, "RACK-101")]:
            await s.execute(
                text(
                    "INSERT INTO locations (id,name,warehouse_id) VALUES (:i,:n,1) ON CONFLICT (id) DO NOTHING"
                ),
                {"i": loc_id, "n": loc_name},
            )
        await s.execute(
            text(
                """
            INSERT INTO items (sku, name, unit)
            SELECT 'SKU-001', 'X猫粮', 'EA'
            WHERE NOT EXISTS (SELECT 1 FROM items WHERE sku='SKU-001')
        """
            )
        )


def _dump_routes(tag: str = "ROUTES"):
    """打印当前进程中的 FastAPI 路由表（path, methods, name）"""
    rows = []
    for r in getattr(app, "routes", []):
        p = getattr(r, "path", None) or getattr(r, "path_format", None)
        if not isinstance(p, str):
            continue
        methods = sorted(list(getattr(r, "methods", []) or []))
        name = getattr(r, "name", "")
        rows.append((p, methods, name))
    print(f"[{tag}] ({len(rows)} total)", *rows, sep="\n  ")


async def _table_has_column(session, table: str, column: str) -> bool:
    rs = await session.execute(
        text("select column_name from information_schema.columns where table_name=:t"),
        {"t": table},
    )
    return any(row[0] == column for row in rs.fetchall())


@pytest.mark.asyncio
async def test_inbound_receive_and_putaway_integrity(async_session_maker):
    """
    严格冒烟（不做自适应）：
      - /scan 收货 10 到暂存位
      - /scan/putaway/commit 上架 7 到 101
      - 校验 (3,7) 与 Σdelta=10
    在用例开始与 /scan 失败时打印路由清单，便于排查 404 原因。
    """
    BATCH = "B20251012-A"

    # 打印一次当前进程的路由表
    _dump_routes("ROUTES@BEGIN")

    # 0) 基线
    await _seed_basic(async_session_maker)

    # 1) 获取 item_id
    async with async_session_maker() as s:
        await s.execute(text("SET search_path TO public"))
        item_id = (await s.execute(text("select id from items where sku='SKU-001'"))).scalar()
        assert item_id, "SKU-001 not found"

    # 2) /scan 收货 10 到暂存位（严格要求 /scan 存在）
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(
            "/scan",
            json={
                "mode": "receive",
                "item_id": int(item_id),
                "warehouse_id": 1,
                "location_id": 0,  # 暂存位
                "qty": 10,
                "ref": "PO-1",
                "batch_code": BATCH,
                "production_date": str(date(2025, 9, 1)),
                "expiry_date": str(date(2026, 9, 1)),
            },
        )
        if r1.status_code != 200:
            # 失败时再次打印路由表，帮助定位为什么 /scan 404
            print("[SCAN-RECEIVE] status:", r1.status_code, "body:", r1.text)
            _dump_routes("ROUTES@SCAN_FAILED")
        assert r1.status_code == 200, f"receive failed: {r1.text}"

        body1 = {}
        try:
            body1 = r1.json()
        except Exception:
            pass
        if isinstance(body1, dict) and "committed" in body1:
            assert body1.get("committed") is True, f"receive not committed: {r1.text}"

    # 3) /scan/putaway/commit 上架 7 到 101
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r_put = await ac.post(
            "/scan/putaway/commit",
            json={
                "item_id": int(item_id),
                "warehouse_id": 1,
                "batch_code": BATCH,
                "qty": 7,
                "from_location_id": 0,
                "location_id": 101,  # 若 orchestrator 期望 to_location_id，Parser 会映射
                "ref": "PW-1",
                "ref_line": 1,
            },
        )
        assert r_put.status_code == 200, f"putaway failed: {r_put.text}"
        body2 = {}
        try:
            body2 = r_put.json()
        except Exception:
            pass
        if isinstance(body2, dict) and "committed" in body2:
            assert body2.get("committed") is True, f"putaway not committed: {r_put.text}"

    # 4) 校验库存与台账
    async with async_session_maker() as s:
        await s.execute(text("SET search_path TO public"))
        tmp_qty = (
            await s.execute(
                text("select qty from stocks where item_id=:i and location_id=0"), {"i": item_id}
            )
        ).scalar() or 0
        loc_qty = (
            await s.execute(
                text("select qty from stocks where item_id=:i and location_id=101"), {"i": item_id}
            )
        ).scalar() or 0
        assert (tmp_qty, loc_qty) == (3, 7), f"stocks mismatch: tmp={tmp_qty}, loc101={loc_qty}"

        sum_delta = (
            await s.execute(
                text("select coalesce(sum(delta),0) from stock_ledger where item_id=:i"),
                {"i": item_id},
            )
        ).scalar() or 0
        assert sum_delta == 10, f"ledger sum delta expected 10, got {sum_delta}"

        if await _table_has_column(s, "stock_ledger", "after_qty"):
            after_tmp = (
                await s.execute(
                    text(
                        """
                select after_qty from stock_ledger
                where item_id=:i and location_id=0 and reason='PUTAWAY'
                order by id desc limit 1
            """
                    ),
                    {"i": item_id},
                )
            ).scalar()
            after_loc = (
                await s.execute(
                    text(
                        """
                select after_qty from stock_ledger
                where item_id=:i and location_id=101 and reason='PUTAWAY'
                order by id desc limit 1
            """
                    ),
                    {"i": item_id},
                )
            ).scalar()
            assert (after_tmp, after_loc) == (
                3,
                7,
            ), f"after_qty mismatch: tmp={after_tmp}, loc101={after_loc}"
