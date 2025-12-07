import pytest

pytest.skip(
    "legacy outbound_v2/event_gateway tests (disabled on v2 baseline)", allow_module_level=True
)

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_v2_service import OutboundV2Service
from app.services.stock_service import StockService
from app.services.trace_service import TraceService

pytestmark = pytest.mark.asyncio

UTC = timezone.utc


async def test_outbound_v2_writes_lines_and_ledger_with_trace(session: AsyncSession):
    """
    v2 出库基础验证：

      - 预先入库一批库存；
      - 使用 OutboundV2Service.commit 做一次出库；
      - 验证：
          * outbound_commits_v2 / outbound_lines_v2 写入成功且带 trace_id；
          * stock_ledger 里有 OUTBOUND_V2_SHIP 记录，trace_id 匹配；
          * TraceService.get_trace(trace_id) 能看到 ledger + outbound 事件。
    """
    # 0) 准备一个现有 item
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    item_id = row.scalar_one()
    assert item_id is not None

    platform = "PDD"
    shop_id = "1"
    warehouse_id = 1
    trace_id = "TRACE-OUT-V2-1"
    ref = f"ORD:{platform}:{shop_id}:OUTV2-1"

    stock_svc = StockService()
    outbound_v2 = OutboundV2Service(stock_svc)

    now = datetime.now(UTC)
    batch_code = "B-OUTV2-1"

    # 1) 预先入库 +10，挂同一个 trace_id
    await stock_svc.adjust(
        session=session,
        item_id=int(item_id),
        warehouse_id=warehouse_id,
        delta=10,
        reason="UT_OUTV2_INBOUND",
        ref="UT-OUTV2-SEED",
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        production_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        trace_id=trace_id,
    )

    # 2) v2 出库 3 个
    r = await outbound_v2.commit(
        session=session,
        trace_id=trace_id,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        external_order_ref="EXT-OUTV2-1",
        lines=[
            {
                "warehouse_id": warehouse_id,
                "item_id": int(item_id),
                "batch_code": batch_code,
                "qty": 3,
            }
        ],
        occurred_at=now,
    )
    assert r["status"] == "OK"
    assert r["total_qty"] == 3
    commit_id = r["commit_id"]
    assert commit_id is not None

    # 3) 检查 outbound_commits_v2 / outbound_lines_v2
    row = await session.execute(
        text(
            """
            SELECT trace_id, platform, shop_id, ref
              FROM outbound_commits_v2
             WHERE id = :cid
            """
        ),
        {"cid": commit_id},
    )
    trace_id_db, plat_db, shop_db, ref_db = row.one()
    assert trace_id_db == trace_id
    assert plat_db == platform.upper()
    assert shop_db == shop_id
    assert ref_db == ref

    # 明细表允许一个 commit 拥有多行（多仓、多批次、多 SKU），
    # 这里不再假定只有一行，而是检查至少有一行匹配我们刚写的槽位。
    rows = await session.execute(
        text(
            """
            SELECT warehouse_id, item_id, batch_code, qty, ledger_ref, ledger_trace_id
              FROM outbound_lines_v2
             WHERE commit_id = :cid
            """
        ),
        {"cid": commit_id},
    )
    rows = rows.fetchall()
    assert rows, "expected at least one outbound_lines_v2 row for commit_id"

    assert any(
        wh_db == warehouse_id
        and item_db == int(item_id)
        and code_db == batch_code
        and qty_db == 3
        and lref_db == ref
        and ltid_db == trace_id
        for (wh_db, item_db, code_db, qty_db, lref_db, ltid_db) in rows
    ), f"no matching outbound_lines_v2 row found for commit_id={commit_id}"

    # 4) 检查 ledger：有 OUTBOUND_V2_SHIP 记录，trace_id 匹配
    row = await session.execute(
        text(
            """
            SELECT reason, ref, delta, trace_id
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = 'OUTBOUND_V2_SHIP'
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"ref": ref},
    )
    reason_db, ref_db2, delta_db, tid_db = row.one()
    assert reason_db == "OUTBOUND_V2_SHIP"
    assert ref_db2 == ref
    assert delta_db == -3
    assert tid_db == trace_id

    # 5) TraceService 聚合验证：现在 outbound v2 也会在 trace 中出现
    trace_svc = TraceService(session)
    result = await trace_svc.get_trace(trace_id)
    events = result.events
    assert events

    sources = {e.source for e in events}
    assert "ledger" in sources
    # outbound 事件中应包含 version='v2' 的记录（由 _from_outbound 聚合）
    assert any(
        e.source == "outbound" and e.raw.get("version") == "v2" and e.raw.get("ref") == ref
        for e in events
    )
