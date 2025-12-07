# tests/api/test_metrics_outbound_api.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.services.stock_service import StockService

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def test_metrics_outbound_today_basic(client, session: AsyncSession):
    """
    基于 vw_outbound_metrics 的 HTTP API 验证：

    - 写一笔 ORDER_CREATED + SHIP_COMMIT 审计；
    - 写一笔 PICK ledger (delta=-3)；
    - 调用 /metrics/outbound/today?platform=PDD，检查：
        * 至少有一行 warehouse_id=1；
        * orders_created >= 1, ship_commits >= 1, pick_qty >= 3。
    """
    platform = "PDD"
    shop_id = "METRICS-API-SHOP"
    ref = f"ORD:{platform}:{shop_id}:API-001"
    item_id = 1001
    wh_id = 1
    batch_code = "API-BATCH-1"

    # 1) 准备库存槽位（stocks + batches）
    await ensure_wh_loc_item(session, wh=wh_id, loc=wh_id, item=item_id)
    await seed_batch_slot(session, item=item_id, loc=wh_id, code=batch_code, qty=10, days=365)

    # 2) 清理旧数据
    await session.execute(
        text("DELETE FROM audit_events WHERE category='OUTBOUND' AND ref=:r"),
        {"r": ref},
    )
    await session.execute(
        text("DELETE FROM stock_ledger WHERE ref=:r"),
        {"r": ref},
    )
    await session.commit()

    # 3) 写 ORDER_CREATED + SHIP_COMMIT 审计
    await session.execute(
        text(
            """
            INSERT INTO audit_events(category, ref, meta, created_at)
            VALUES ('OUTBOUND', :r, '{"flow":"OUTBOUND","event":"ORDER_CREATED","platform":"PDD"}'::jsonb, now())
            """
        ),
        {"r": ref},
    )
    await session.execute(
        text(
            """
            INSERT INTO audit_events(category, ref, meta, created_at)
            VALUES ('OUTBOUND', :r, '{"flow":"OUTBOUND","event":"SHIP_COMMIT","platform":"PDD"}'::jsonb, now())
            """
        ),
        {"r": ref},
    )

    # 4) 写一条 PICK ledger delta=-3
    stock_svc = StockService()
    now = datetime.now(UTC)
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=wh_id,
        delta=-3,
        reason="PICK",
        ref=ref,
        ref_line=1,
        occurred_at=now,
        batch_code=batch_code,
        trace_id="TRACE-METRICS-1",
    )

    await session.commit()

    # 5) 调 metrics API
    resp = await client.get("/metrics/outbound/today", params={"platform": platform})
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["platform"] == platform
    # day 只要是今天即可（不强制检查）

    warehouses = data["warehouses"]
    assert isinstance(warehouses, list)
    assert warehouses, "expected at least one warehouse metrics row"

    # 查找 wh1 的指标
    w1 = next((w for w in warehouses if w["warehouse_id"] == wh_id), None)
    assert w1 is not None, "expected metrics row for warehouse_id=1"

    assert w1["orders_created"] >= 1
    assert w1["ship_commits"] >= 1
    assert w1["pick_qty"] >= 3
