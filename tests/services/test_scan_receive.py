# tests/services/test_scan_receive.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.procurement.services.inbound_service import InboundService
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc


@pytest.mark.asyncio
async def test_scan_receive_commits_ledger(session: AsyncSession):
    """
    v2 入库服务测试（warehouse + item + batch 粒度）：

    - 通过 InboundService.receive 使用 sku 查找 item。
    - Phase M-5：stocks_lot.lot_id NOT NULL；“无批次”由 lots.lot_code 为 NULL 表达（INTERNAL lot）。
    - 因此槽位定位统一通过 lots.lot_code IS NOT DISTINCT FROM :batch_code。
    """
    warehouse_id = 1
    sku = "SKU-TEST-INBOUND-3001"
    batch_code = "RCV-3001"
    qty = 3
    expiry = date.today() + timedelta(days=365)
    ref = f"IN-{int(datetime.now(UTC).timestamp())}"

    svc = InboundService()

    # ✅ Phase M：items policy NOT NULL；测试侧预先建好 item
    await ensure_item(session, id=4003, sku=sku, name=sku, uom="EA", expiry_required=False)
    await session.commit()

    res = await svc.receive(
        session=session,
        item_id=None,
        sku=sku,
        qty=qty,
        ref=ref,
        occurred_at=datetime.now(UTC),
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        expiry_date=expiry,
    )

    item_id = res["item_id"]
    assert item_id > 0
    assert res["warehouse_id"] == warehouse_id
    assert res.get("batch_code") in (batch_code, None)
    assert res["qty"] == qty

    eff_code = res.get("batch_code")

    # DB 事实：stocks_lot.lot_id NOT NULL；用 lots.lot_code（可 NULL）筛选槽位
    row = await session.execute(
        text(
            """
            SELECT COALESCE(SUM(sl.qty), 0) AS qty
              FROM stocks_lot sl
              LEFT JOIN lots lo ON lo.id = sl.lot_id
             WHERE sl.item_id = :i
               AND sl.warehouse_id = :w
               AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": eff_code},
    )
    db_qty = int(row.scalar_one_or_none() or 0)
    assert db_qty == qty
