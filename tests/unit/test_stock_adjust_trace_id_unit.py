from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def test_stock_adjust_writes_trace_id(session: AsyncSession):
    """
    验证 StockService.adjust 会把 trace_id 落在 stock_ledger.trace_id 上。

    步骤：
      1) 从 items 表拿一条现有 item_id；
      2) 调用 adjust 做一次入库（delta>0），带上 trace_id='TR-UNIT-1'；
      3) 在同一个测试中查询 stock_ledger，按 ref='UT-ADJUST-1' 过滤；
      4) 断言存在一条记录，且 trace_id='TR-UNIT-1'。
    """
    svc = StockService()
    now = datetime.now(UTC)

    # 1) 取一个已经存在的 item_id，避免触发 batches.item_id 外键错误
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    item_id = row.scalar_one()
    assert item_id is not None

    # 2) 入库：让 adjust 帮我们建 batch + stocks + ledger
    ref = "UT-ADJUST-1"
    trace_id = "TR-UNIT-1"

    await svc.adjust(
        session=session,
        scope="PROD",
        item_id=int(item_id),
        warehouse_id=1,
        delta=5,
        reason="UNIT_INBOUND",
        ref=ref,
        ref_line=1,
        occurred_at=now,
        batch_code="B-UT-1",
        production_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        trace_id=trace_id,
    )

    # 3) 查询 ledger，确认 trace_id 已经写入
    row = await session.execute(
        text(
            """
            SELECT trace_id
              FROM stock_ledger
             WHERE scope='PROD'
               AND ref = :ref
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"ref": ref},
    )
    result = row.scalar_one_or_none()

    assert result == trace_id
