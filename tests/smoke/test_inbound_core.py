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
        text(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = :t
            """
        ),
        {"t": table},
    )
    return any(row[0] == column for row in rs.fetchall())


@pytest.mark.asyncio
async def test_inbound_receive_and_putaway_integrity(async_session_maker):
    """
    严格冒烟（不做自适应）：
      - /scan 收货 10 到暂存位
      - /scan/putaway/commit 上架 7 到 101
      - 校验 Σdelta=10，且 ledger 的 after_qty 反映 (3,7)

    如果后端返回 FEATURE_DISABLED: putaway，说明 scan+putaway 特性在当前环境关闭，
    本用例将直接 skip，而不是红炸。
    """
    BATCH = "B20251012-A"
    PROD = date(2025, 9, 1)
    EXP = date(2026, 9, 1)

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
                "location_id": 0,  # 暂存位（receive 阶段仍然使用 location_id）
                "qty": 10,
                "ref": "PO-1",
                "batch_code": BATCH,
                "production_date": str(PROD),
                "expiry_date": str(EXP),
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
            body1 = {}
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
                "to_location_id": 101,  # v2 模型要求显式 to_location_id
                # v2 约束：有搬运就要带生产/到期日期
                "production_date": str(PROD),
                "expiry_date": str(EXP),
                "ref": "PW-1",
                "ref_line": 1,
            },
        )
        if r_put.status_code != 200:
            print("[SCAN-PUTAWAY] status:", r_put.status_code, "body:", r_put.text)
        assert r_put.status_code == 200, f"putaway failed: {r_put.text}"

        body2 = {}
        try:
            body2 = r_put.json()
        except Exception:
            body2 = {}

        # 若后端明确返回 FEATURE_DISABLED: putaway，则视为当前环境关闭该特性，直接跳过
        if isinstance(body2, dict):
            errors = body2.get("errors") or []
            if any("FEATURE_DISABLED: putaway" in str(e) for e in errors):
                pytest.skip(
                    "scan putaway feature disabled (FEATURE_DISABLED: putaway)，跳过完整收货+上架冒烟"
                )
            if "committed" in body2:
                assert body2.get("committed") is True, f"putaway not committed: {r_put.text}"

    # 4) 校验库存与台账（stocks 已不再按 location 维度建模，只验证总量 + ledger）
    async with async_session_maker() as s:
        await s.execute(text("SET search_path TO public"))

        # v2 stocks：按 (warehouse_id, item_id, batch_code) 聚合
        total_qty = (
            await s.execute(
                text(
                    """
                SELECT COALESCE(qty, 0)
                  FROM stocks
                 WHERE warehouse_id = 1
                   AND item_id      = :i
                   AND batch_code   = :b
                """
                ),
                {"i": item_id, "b": BATCH},
            )
        ).scalar() or 0
        assert total_qty == 10, f"stocks total qty mismatch: expected 10, got {total_qty}"

        # Σdelta 必须为 10
        sum_delta = (
            await s.execute(
                text("select coalesce(sum(delta),0) from stock_ledger where item_id=:i"),
                {"i": item_id},
            )
        ).scalar() or 0
        assert sum_delta == 10, f"ledger sum delta expected 10, got {sum_delta}"

        # 若有 after_qty + location_id，进一步验证 (3,7) 的位置分布
        has_after = await _table_has_column(s, "stock_ledger", "after_qty")
        has_loc = await _table_has_column(s, "stock_ledger", "location_id")
        if has_after and has_loc:
            after_tmp = (
                await s.execute(
                    text(
                        """
                SELECT after_qty
                  FROM stock_ledger
                 WHERE item_id=:i
                   AND location_id=0
                   AND reason='PUTAWAY'
                 ORDER BY id DESC
                 LIMIT 1
            """
                    ),
                    {"i": item_id},
                )
            ).scalar()
            after_loc = (
                await s.execute(
                    text(
                        """
                SELECT after_qty
                  FROM stock_ledger
                 WHERE item_id=:i
                   AND location_id=101
                   AND reason='PUTAWAY'
                 ORDER BY id DESC
                 LIMIT 1
            """
                    ),
                    {"i": item_id},
                )
            ).scalar()
            assert (after_tmp, after_loc) == (
                3,
                7,
            ), f"after_qty mismatch: tmp={after_tmp}, loc101={after_loc}"
