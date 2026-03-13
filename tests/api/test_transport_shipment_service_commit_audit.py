# tests/api/test_transport_shipment_service_commit_audit.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tms.shipment import ShipCommitAuditCommand, TransportShipmentService

pytestmark = pytest.mark.asyncio


async def test_transport_shipment_service_commit_audit_writes_audit(session: AsyncSession) -> None:
    """
    最小合同：TransportShipmentService.ship_commit_audit 会写
    OUTBOUND / SHIP_COMMIT 审计事件。

    - 使用固定 ref 清理历史审计；
    - 调用 TransportShipmentService(session).ship_commit_audit(...) 一次；
    - 校验 audit_events 至少写入一条对应记录。
    """
    ref = "UT-SHIP-SVC-001"
    platform = "INTERNAL"
    shop_id = "NO-STORE"
    trace_id = "TRACE-UT-SHIP-001"

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

    svc = TransportShipmentService(session)

    resp = await svc.ship_commit_audit(
        ShipCommitAuditCommand(
            ref=ref,
            platform=platform,
            shop_id=shop_id,
            trace_id=trace_id,
            meta={"carrier": "DUMMY", "tracking_no": "T123456"},
        )
    )
    assert resp.ok is True
    assert resp.ref == ref
    assert resp.trace_id == trace_id

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
