from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import async_session_maker
from app.main import app

pytestmark = pytest.mark.smoke


async def _seed_basic():
    """预置最小维度：Warehouse(id=1)、SKU 与两个库位（0=暂存，101=目标货架）。
    使用 ON CONFLICT DO NOTHING（PG/SQLite 通用）实现幂等插入。
    """
    async with async_session_maker() as s, s.begin():
        # 1) 仓库（供库位外键使用）
        await s.execute(
            text(
                """
            INSERT INTO warehouses (id, name)
            VALUES (1, 'WH-TEST')
            ON CONFLICT (id) DO NOTHING
        """
            )
        )

        # 2) 物料
        await s.execute(
            text(
                """
            INSERT INTO items (id, sku, name, unit)
            VALUES (1,'SKU-001','X猫粮','EA')
            ON CONFLICT (id) DO NOTHING
        """
            )
        )

        # 3) 库位（带上 warehouse_id，兼容 NOT NULL + FK 约束）
        for loc_id, loc_name in [(0, "STAGE"), (101, "RACK-101")]:
            await s.execute(
                text(
                    """
                INSERT INTO locations (id, name, warehouse_id)
                VALUES (:i, :n, 1)
                ON CONFLICT (id) DO NOTHING
            """
                ),
                {"i": loc_id, "n": loc_name},
            )


async def _table_has_column(session, table: str, column: str) -> bool:
    """检测列存在性（SQLite/PG 兼容），用于有/无 after_qty 情况下的柔性断言。"""
    # SQLite: PRAGMA table_info
    try:
        rs = await session.execute(text(f"PRAGMA table_info({table});"))
        cols = {row[1] for row in rs.fetchall()}
        if cols:
            return column in cols
    except Exception:
        pass
    # PG: information_schema
    try:
        rs = await session.execute(
            text(
                """
            select column_name from information_schema.columns
            where table_name = :t
        """
            ),
            {"t": table},
        )
        cols = {row[0] for row in rs.fetchall()}
        return column in cols
    except Exception:
        return False


@pytest.mark.asyncio
async def test_inbound_receive_and_putaway_integrity():
    await _seed_basic()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1) INBOUND 10 到暂存区
        r1 = await ac.post(
            "/inbound/receive",
            json={
                "sku": "SKU-001",
                "qty": 10,
                "batch_code": "B20251012-A",
                "production_date": str(date(2025, 9, 1)),
                "expiry_date": str(date(2026, 9, 1)),
                "ref": "PO-1",
                "ref_line": "L1",
            },
        )
        assert r1.status_code == 200, f"receive failed: {r1.text}"

        # 2) PUTAWAY 7 到库位 101
        r2 = await ac.post(
            "/inbound/putaway",
            json={
                "sku": "SKU-001",
                "batch_code": "B20251012-A",
                "qty": 7,
                "to_location_id": 101,
                "ref": "PW-1",
                "ref_line": "L1",
            },
        )
        assert r2.status_code == 200, f"putaway failed: {r2.text}"

    # 3) 账实一致：暂存=3、库位101=7；并做 ledger Σdelta 与 after_qty（若列存在）校验
    async with async_session_maker() as s:
        tmp_qty = (
            await s.execute(text("select qty from stocks where item_id=1 and location_id=0"))
        ).scalar() or 0
        loc_qty = (
            await s.execute(text("select qty from stocks where item_id=1 and location_id=101"))
        ).scalar() or 0
        assert (tmp_qty, loc_qty) == (3, 7), f"stocks mismatch: tmp={tmp_qty}, loc101={loc_qty}"

        # Σdelta：INBOUND(+10) + PUTAWAY(-7/+7) => 总和应为 10
        sum_delta = (
            await s.execute(text("select coalesce(sum(delta),0) from stock_ledger where item_id=1"))
        ).scalar() or 0
        assert sum_delta == 10, f"ledger sum delta expected 10, got {sum_delta}"

        # 若存在 after_qty 列，则校验两条 PUTAWAY 的快照各自等于 3 与 7
        if await _table_has_column(s, "stock_ledger", "after_qty"):
            # 暂存端 after_qty == 3
            after_tmp = (
                await s.execute(
                    text(
                        """
                select after_qty from stock_ledger
                where item_id=1 and location_id=0 and op='PUTAWAY'
                order by id desc limit 1
            """
                    )
                )
            ).scalar()
            # 目标位 after_qty == 7
            after_loc = (
                await s.execute(
                    text(
                        """
                select after_qty from stock_ledger
                where item_id=1 and location_id=101 and op='PUTAWAY'
                order by id desc limit 1
            """
                    )
                )
            ).scalar()
            assert (
                after_tmp == 3 and after_loc == 7
            ), f"after_qty mismatch: tmp={after_tmp}, loc101={after_loc}"


@pytest.mark.asyncio
async def test_invalid_barcode_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/inbound/scan", json={"barcode": "xyz"})
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        assert r.json().get("detail") in {"INVALID_BARCODE", "INVALID_BARCODE_FORMAT"}, r.text


@pytest.mark.asyncio
async def test_expiry_conflict_422():
    await _seed_basic()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(
            "/inbound/receive",
            json={
                "sku": "SKU-001",
                "qty": 1,
                "batch_code": "B-EXP",
                "production_date": "2025-09-01",
                "expiry_date": "2026-09-01",
                "ref": "PO-2",
                "ref_line": "L1",
            },
        )
        assert r1.status_code == 200, f"first receive failed: {r1.text}"

        # 同批次但不同效期 -> 422
        r2 = await ac.post(
            "/inbound/receive",
            json={
                "sku": "SKU-001",
                "qty": 1,
                "batch_code": "B-EXP",
                "production_date": "2025-09-01",
                "expiry_date": "2027-09-01",
                "ref": "PO-3",
                "ref_line": "L1",
            },
        )
        assert r2.status_code == 422, f"expected 422, got {r2.status_code}: {r2.text}"
        assert r2.json()["detail"] in {"BATCH_EXPIRY_CONFLICT", "BATCH_CONFLICT"}, r2.text


@pytest.mark.asyncio
async def test_putaway_negative_409():
    await _seed_basic()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r1 = await ac.post(
            "/inbound/receive",
            json={
                "sku": "SKU-001",
                "qty": 2,
                "batch_code": "B-NEG",
                "ref": "PO-4",
                "ref_line": "L1",
            },
        )
        assert r1.status_code == 200, f"seed receive failed: {r1.text}"

        r2 = await ac.post(
            "/inbound/putaway",
            json={
                "sku": "SKU-001",
                "batch_code": "B-NEG",
                "qty": 5,
                "to_location_id": 101,
                "ref": "PW-NEG",
                "ref_line": "L1",
            },
        )
        assert r2.status_code in (409, 422), f"expected 409/422, got {r2.status_code}: {r2.text}"


@pytest.mark.asyncio
async def test_idempotent_409_on_duplicate_refline():
    await _seed_basic()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {
            "sku": "SKU-001",
            "qty": 1,
            "batch_code": "B-IDEMP",
            "ref": "PO-5",
            "ref_line": "L1",
        }
        r1 = await ac.post("/inbound/receive", json=body)
        assert r1.status_code == 200, f"first receive failed: {r1.text}"

        r2 = await ac.post("/inbound/receive", json=body)
        # 你实现成 409 最清晰；如果是“Already Reported”也接受 208
        assert r2.status_code in (409, 208), f"expected 409/208, got {r2.status_code}: {r2.text}"
