# tests/api/test_ship_service_commit_writes_audit.py
# tests/api/test_ship_service_commit_writes_audit.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ship_service import ShipService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_ship_service_commit_writes_audit(session: AsyncSession):
    """
    最小合同：ShipService.commit 会写 OUTBOUND / SHIP_COMMIT 审计事件。

    - 使用固定 ref 清理历史审计；
    - 调用 ShipService(session).commit(...) 一次；
    - 校验 audit_events 至少写入一条对应记录。
    """
    ref = "UT-SHIP-SVC-001"
    platform = "INTERNAL"
    shop_id = "NO-STORE"
    trace_id = "TRACE-UT-SHIP-001"

    # 清理同 ref 的历史审计
    await session.execute(
        text(
            """
            DELETE FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :r
               AND (meta->>'event') = 'SHIP_COMMIT'
            """
        ),
        {"r": ref},
    )
    await session.commit()

    svc = ShipService(session)

    resp = await svc.commit(
        ref=ref,
        platform=platform,
        shop_id=shop_id,
        trace_id=trace_id,
        meta={"carrier": "DUMMY", "tracking_no": "T123456"},
    )
    assert resp["ok"] is True
    assert resp["ref"] == ref
    assert resp["trace_id"] == trace_id

    # 校验 audit_events 中确实写入记录
    rec = await session.execute(
        text(
            """
            SELECT COUNT(*)
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :r
               AND (meta->>'flow')  = 'OUTBOUND'
               AND (meta->>'event') = 'SHIP_COMMIT'
            """
        ),
        {"r": ref},
    )
    cnt = int(rec.scalar() or 0)
    assert cnt >= 1
