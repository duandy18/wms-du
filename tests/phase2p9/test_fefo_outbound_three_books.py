# tests/phase2p9/test_fefo_outbound_three_books.py
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.fefo_allocator import FefoAllocator
from app.services.snapshot_v3_service import SnapshotV3Service
from app.services.stock_service import StockService

UTC = timezone.utc


@pytest.mark.pre_pilot
@pytest.mark.asyncio
async def test_fefo_ship_and_three_books_consistency(
    db_session_like_pg: AsyncSession,
) -> None:
    """
    FEFO + 三本账一致性测试（核心体检案例）

    场景：
      - 仓库=1，item=1（如需可改）
      - 入库三批：
          A: exp 2025-01-10, qty=10
          B: exp 2025-01-20, qty=20
          C: exp 2025-02-01, qty=30
      - FEFO 出库 40 → 期望：A10 + B20 + C10
      - 出库后库存应为：
          A=0, B=0, C=20
      - 最后 snapshot_v3 基于 ledger 重算，再 compare 三本账 → diff 全为 0
    """

    session: AsyncSession = db_session_like_pg
    stock = StockService()
    fefo = FefoAllocator()

    wh_id = 1
    item_id = 1

    # ---------- 0. 清理库存相关表 ----------
    await session.execute(text("DELETE FROM stock_snapshots"))
    await session.execute(text("DELETE FROM stock_ledger"))
    await session.execute(text("DELETE FROM stocks"))
    await session.execute(text("DELETE FROM batches"))

    # 注意：fixture 外面已经有大事务，这里不用再 begin/commit，
    # 同一个 Session 里 DML + 查询都可见。

    # ---------- 1. 入库三批 ----------
    trace_id = "TRACE-FEFO-THREE-BOOKS"
    in_ts = datetime(2025, 1, 1, 8, 0, tzinfo=UTC)

    # A
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        delta=10,
        reason=MovementType.RECEIPT,
        ref="FEFO-IN",
        ref_line=1,
        occurred_at=in_ts,
        batch_code="BATCH-A",
        production_date=date(2024, 12, 1),
        expiry_date=date(2025, 1, 10),
        trace_id=trace_id,
    )
    # B
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        delta=20,
        reason=MovementType.RECEIPT,
        ref="FEFO-IN",
        ref_line=2,
        occurred_at=in_ts,
        batch_code="BATCH-B",
        production_date=date(2024, 12, 5),
        expiry_date=date(2025, 1, 20),
        trace_id=trace_id,
    )
    # C
    await stock.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        delta=30,
        reason=MovementType.RECEIPT,
        ref="FEFO-IN",
        ref_line=3,
        occurred_at=in_ts,
        batch_code="BATCH-C",
        production_date=date(2024, 12, 10),
        expiry_date=date(2025, 2, 1),
        trace_id=trace_id,
    )

    # ---------- sanity：入库结果 ----------
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT batch_code, qty
                FROM stocks
                WHERE warehouse_id = :w AND item_id = :i
                ORDER BY batch_code
                """
                ),
                {"w": wh_id, "i": item_id},
            )
        )
        .mappings()
        .all()
    )
    assert {r["batch_code"]: int(r["qty"]) for r in rows} == {
        "BATCH-A": 10,
        "BATCH-B": 20,
        "BATCH-C": 30,
    }

    # ---------- 2. FEFO 计划 ----------
    plan = await fefo.plan(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        need=40,
        occurred_date=date(2025, 1, 5),
        allow_expired=False,
    )
    # 按 expiry_date 升序：A(10) → B(20) → C(10)
    assert plan == [
        ("BATCH-A", 10),
        ("BATCH-B", 20),
        ("BATCH-C", 10),
    ]

    # ---------- 3. FEFO ship 出库 ----------
    ship_ts = datetime(2025, 1, 5, 10, 0, tzinfo=UTC)

    res = await fefo.ship(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        qty=40,
        ref="FEFO-OUT",
        occurred_at=ship_ts,
        reason=MovementType.SHIPMENT,
        allow_expired=False,
        trace_id=trace_id,
    )

    assert res["ok"] is True
    assert res["total"] == 40
    assert [leg["batch_code"] for leg in res["legs"]] == ["BATCH-A", "BATCH-B", "BATCH-C"]
    assert [leg["delta"] for leg in res["legs"]] == [-10, -20, -10]

    # ---------- 出库后的库存 ----------
    rows_after = (
        (
            await session.execute(
                text(
                    """
                SELECT batch_code, qty
                FROM stocks
                WHERE warehouse_id = :w AND item_id = :i
                ORDER BY batch_code
                """
                ),
                {"w": wh_id, "i": item_id},
            )
        )
        .mappings()
        .all()
    )

    assert {r["batch_code"]: int(r["qty"]) for r in rows_after} == {
        "BATCH-A": 0,
        "BATCH-B": 0,
        "BATCH-C": 20,
    }

    # ---------- 4. snapshot_v3 → 重建快照 + 三本账对账 ----------
    snap_v3 = SnapshotV3Service()
    cut_ts = datetime(2025, 1, 6, 0, 0, tzinfo=UTC)

    # 用 ledger 重建 cut_ts 当日快照
    await snap_v3.rebuild_snapshot_from_ledger(session, snapshot_date=cut_ts)
    # 对账：ledger_cut vs snapshot vs stocks
    compare = await snap_v3.compare_snapshot(session, snapshot_date=cut_ts)

    for r in compare["rows"]:
        assert int(r["diff_snapshot"]) == 0, f"snapshot mismatch: {r}"
        assert int(r["diff_stock"]) == 0, f"stock mismatch: {r}"
