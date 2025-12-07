from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ship_service import ShipService


@pytest.mark.asyncio
async def test_ship_service_commit_is_idempotent(session: AsyncSession):
    """
    ShipService.commit 只写 audit_events，不碰库存：

      - 若 audit_events 表不存在：
          * 第一次返回 SKIPPED
          * 第二次也返回 SKIPPED
      - 若 audit_events 表存在：
          * 第一次可能是 OK（首次写入）或 IDEMPOTENT（基线已存在）
          * 第二次必须是 IDEMPOTENT
          * 第二次调用不会增加匹配行的数量
    """
    ref = "SHIP-AUDIT-1"
    occurred_at = datetime.now(timezone.utc)

    svc = ShipService()

    r1 = await svc.commit(
        session,
        ref=ref,
        occurred_at=occurred_at,
        platform="PDD",
        shop_id="SHOP1",
        carrier="SF",
        tracking_no="SF123456",
    )

    # 情况 1：没有 audit_events 表 → 两次都 SKIPPED
    if r1["status"] == "SKIPPED":
        r2 = await svc.commit(
            session,
            ref=ref,
            occurred_at=occurred_at,
            platform="PDD",
            shop_id="SHOP1",
            carrier="SF",
            tracking_no="SF123456",
        )
        assert r2["status"] == "SKIPPED"
        return

    # 情况 2：有 audit_events 表
    # 先数一数当前匹配的行数（可能是 0/1/更多，取决于基线和 r1 的行为）
    row = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE category='OUTBOUND'
              AND ref=:ref
              AND (meta->>'flow')='OUTBOUND'
              AND (meta->>'event')='SHIP_COMMIT'
            """
        ),
        {"ref": ref},
    )
    count_before = row.scalar_one()

    # 第二次调用，必须 IDEMPOTENT，且不会增加匹配行数
    r2 = await svc.commit(
        session,
        ref=ref,
        occurred_at=occurred_at,
        platform="PDD",
        shop_id="SHOP1",
        carrier="SF",
        tracking_no="SF123456",
    )
    assert r2["status"] == "IDEMPOTENT"

    row = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE category='OUTBOUND'
              AND ref=:ref
              AND (meta->>'flow')='OUTBOUND'
              AND (meta->>'event')='SHIP_COMMIT'
            """
        ),
        {"ref": ref},
    )
    count_after = row.scalar_one()

    # 幂等要求：第二次调用不增加行数
    assert count_after == count_before
