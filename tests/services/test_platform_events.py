# tests/services/test_platform_events.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_events import handle_event_batch

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_platform_event_basic_flow(session: AsyncSession):
    # 模拟一个“已支付”事件（将触发 reserve 分支；不直动 stocks）
    ev = [
        {
            "platform": "pdd",
            "shop_id": "S1",
            "order_sn": "O1",
            "status": "PAID",
            "lines": [{"item_id": 3001, "qty": 1}],
        }
    ]
    await handle_event_batch(ev, session=session)

    # 有事件入库（source 由服务内部统一写入）
    row = (await session.execute(text("SELECT COUNT(*) FROM event_log"))).scalar_one()
    assert int(row) >= 1
