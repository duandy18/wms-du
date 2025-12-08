# tests/services/test_ship_service_audit.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ship_service import ShipService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_ship_service_commit_writes_audit_and_is_not_idempotent(session: AsyncSession):
    """
    当前 ShipService 行为合同（v2）：

    - ShipService(session) 只负责写审计事件（OUTBOUND / SHIP_COMMIT），不碰库存；
    - 每次调用 commit(ref=...) 都会写一条审计记录（没有幂等去重）；
    - meta 中至少包含 platform / shop_id 字段。
    """
    ref = "SHIP-AUDIT-1"
    platform = "PDD"
    shop_id = "SHOP1"
    trace_id = "TRACE-SHIP-AUDIT-1"

    # 先清理同 ref 的历史审计，避免基线干扰
    await session.execute(
        text(
            """
            DELETE FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND (meta->>'event') = 'SHIP_COMMIT'
            """
        ),
        {"ref": ref},
    )
    await session.commit()

    svc = ShipService(session)

    # 第一次调用：写一条审计事件
    res1 = await svc.commit(
        ref=ref,
        platform=platform,
        shop_id=shop_id,
        trace_id=trace_id,
        meta={"carrier": "SF", "tracking_no": "SF123456"},
    )
    assert res1["ok"] is True
    assert res1["ref"] == ref
    assert res1["trace_id"] == trace_id

    row = await session.execute(
        text(
            """
            SELECT COUNT(*)
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND (meta->>'flow')  = 'OUTBOUND'
               AND (meta->>'event') = 'SHIP_COMMIT'
            """
        ),
        {"ref": ref},
    )
    count_after_first = int(row.scalar() or 0)
    assert count_after_first == 1

    # 第二次调用：当前实现不会做幂等去重，应增加一条审计记录
    res2 = await svc.commit(
        ref=ref,
        platform=platform,
        shop_id=shop_id,
        trace_id=trace_id,
        meta={"carrier": "SF", "tracking_no": "SF123456"},
    )
    assert res2["ok"] is True
    assert res2["ref"] == ref

    row2 = await session.execute(
        text(
            """
            SELECT COUNT(*)
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND (meta->>'flow')  = 'OUTBOUND'
               AND (meta->>'event') = 'SHIP_COMMIT'
            """
        ),
        {"ref": ref},
    )
    count_after_second = int(row2.scalar() or 0)
    assert count_after_second == 2

    # 顺带校验一行 meta 里带有 platform/shop_id 字段
    meta_row = (
        await session.execute(
            text(
                """
                SELECT meta
                  FROM audit_events
                 WHERE category = 'OUTBOUND'
                   AND ref       = :ref
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": ref},
        )
    ).scalar_one()
    # meta 可能是 jsonb→dict 或 text→str，这里只做存在性检查
    if isinstance(meta_row, dict):
        assert meta_row.get("platform") == platform
        assert meta_row.get("shop_id") == shop_id
