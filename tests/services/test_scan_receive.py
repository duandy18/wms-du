# tests/services/test_scan_receive.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc


@pytest.mark.asyncio
async def test_scan_receive_commits_ledger(session: AsyncSession):
    """
    v2 入库服务测试（warehouse + item + batch 粒度）：

    - 不依赖 location_id，也不依赖 tests.utils 中的 helper。
    - 通过 InboundService.receive 使用 sku 自动建 item。
    - Phase 4E：lot-world 口径，校验 stocks_lot 的 qty 被正确更新。
      * 若该入库落到 lot 槽位：通过 lots.lot_code 定位
      * 若该入库被归一到 NULL 槽位：使用 lot_id_key=0 定位
    """

    warehouse_id = 1
    sku = "SKU-TEST-INBOUND-3001"
    batch_code = "RCV-3001"
    qty = 3
    expiry = date.today() + timedelta(days=365)
    ref = f"IN-{int(datetime.now(UTC).timestamp())}"

    svc = InboundService()

    # ✅ Phase M：items policy NOT NULL；InboundService 的“自动建档”旧 insert 可能不补齐 policy
    # 测试侧预先建好 item（用固定 id，避免每次跑序列不同）
    await ensure_item(session, id=4003, sku=sku, name=sku, uom="EA", expiry_required=False)
    await session.commit()

    # 不再显式 session.begin()，session fixture 已经管理事务
    res = await svc.receive(
        session=session,
        # 不提供 item_id，改用 sku，由 InboundService._ensure_item_id 查找已有记录
        item_id=None,
        sku=sku,
        qty=qty,
        ref=ref,
        occurred_at=datetime.now(UTC),
        warehouse_id=warehouse_id,
        batch_code=batch_code,
        expiry_date=expiry,
    )

    # 返回值基本字段校验
    item_id = res["item_id"]
    assert item_id > 0
    assert res["warehouse_id"] == warehouse_id
    # Phase L：若 item 默认为非效期（NONE），batch_code 将被语义层强制归一为 NULL。
    # 因此这里只断言“返回 batch_code 要么为输入值，要么为 None（NONE 模式）”。
    assert res.get("batch_code") in (batch_code, None)
    assert res["qty"] == qty

    # Phase 4E：优先按 lot_code（lots）定位；如果没有 lot（lot_id 为 NULL），则落在 lot_id_key=0
    eff_code = res.get("batch_code")
    row = await session.execute(
        text(
            """
            SELECT sl.qty
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.item_id = :i
               AND sl.warehouse_id = :w
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"i": item_id, "w": warehouse_id, "c": str(eff_code or "")},
    )
    v = row.scalar_one_or_none()
    if v is None:
        row2 = await session.execute(
            text(
                """
                SELECT sl.qty
                  FROM stocks_lot sl
                 WHERE sl.item_id = :i
                   AND sl.warehouse_id = :w
                   AND sl.lot_id_key = 0
                 LIMIT 1
                """
            ),
            {"i": item_id, "w": warehouse_id},
        )
        v2 = row2.scalar_one_or_none()
        assert v2 is not None, "expected stocks_lot row for NULL lot slot (lot_id_key=0)"
        db_qty = int(v2)
    else:
        db_qty = int(v)

    assert db_qty == qty
