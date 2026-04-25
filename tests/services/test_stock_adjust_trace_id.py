from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lots import ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def test_stock_adjust_writes_trace_id(session: AsyncSession):
    """
    验证 lot-only 写入原语会把 trace_id 落在 stock_ledger.trace_id 上。

    说明：
      - 这是“技术链路锚点”测试，不是“业务事件锚点”测试。
      - 当前 stock adjust 原语入口并不要求一定创建 wms_events 头，
        因此这里不对 stock_ledger.event_id 做强断言，只确认 trace_id 可追踪。

    步骤：
      1) 从 items 表拿一条现有 item_id；
      2) 创建/复用 SUPPLIER lot；
      3) 调用 adjust_lot_impl 做一次入库（delta>0），带上 trace_id='TR-UNIT-1'；
      4) 在同一个测试中查询 stock_ledger，按 ref='UT-ADJUST-1' 过滤；
      5) 断言存在一条记录，且 trace_id='TR-UNIT-1'。
    """
    now = datetime.now(UTC)

    # 1) 取一个已经存在的 item_id，避免触发 items 外键错误（Phase 4E：批次主档已迁移到 lots）
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    item_id = row.scalar_one()
    assert item_id is not None

    # 2) 入库：让 lot-only primitive 写入 lot-world：lots + stocks_lot + ledger
    ref = "UT-ADJUST-1"
    trace_id = "TR-UNIT-1"
    production_date = date.today()
    expiry_date = production_date + timedelta(days=365)

    lot_id = await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=1,
        lot_code="B-UT-1",
        production_date=production_date,
        expiry_date=expiry_date,
    )

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=1,
        lot_id=int(lot_id),
        delta=5,
        reason="UNIT_INBOUND",
        ref=ref,
        ref_line=1,
        occurred_at=now,
        meta=None,
        batch_code="B-UT-1",
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
        utc_now=lambda: datetime.now(UTC),
    )

    # 3) 查询 ledger，确认 trace_id 已经写入
    row = await session.execute(
        text(
            """
            SELECT trace_id, event_id
              FROM stock_ledger
             WHERE ref = :ref
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"ref": ref},
    )
    result = row.mappings().first()

    assert result is not None
    assert str(result["trace_id"]) == trace_id
