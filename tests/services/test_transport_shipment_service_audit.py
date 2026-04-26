# tests/services/test_transport_shipment_service_audit.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shipping_assist.shipment import ShipCommitAuditCommand, TransportShipmentService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session(async_session_maker) -> AsyncSession:
    """
    复用 async_session_maker 构造一次性会话。
    """
    async with async_session_maker() as sess:
        yield sess


async def test_transport_shipment_service_ship_commit_audit_writes_audit(session: AsyncSession) -> None:
    """
    验证 TransportShipmentService.ship_commit_audit 会写一条
    OUTBOUND / SHIP_COMMIT 审计事件到 audit_events。
    """
    svc = TransportShipmentService(session)
    ref = "SHIP-UNIT-001"
    platform = "PDD"
    store_code = "1"
    trace_id = "TRACE-SHIP-001"

    result = await svc.ship_commit_audit(
        ShipCommitAuditCommand(
            ref=ref,
            platform=platform,
            store_code=store_code,
            trace_id=trace_id,
            meta={"foo": "bar"},
        )
    )
    assert result.ok is True
    assert result.ref == ref
    assert result.trace_id == trace_id

    row = (
        await session.execute(
            text(
                """
                SELECT category, ref, meta, trace_id
                  FROM audit_events
                 WHERE ref = :ref
                   AND category = 'OUTBOUND'
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": ref},
        )
    ).first()

    assert row is not None
    category, ref_db, meta_db, trace_db = row
    assert category == "OUTBOUND"
    assert ref_db == ref
    assert trace_db == trace_id

    assert isinstance(meta_db, dict)
    assert meta_db["flow"] == "OUTBOUND"
    assert meta_db["event"] == "SHIP_COMMIT"
    assert meta_db["platform"] == platform.upper()
    assert meta_db["store_code"] == store_code
    assert meta_db["foo"] == "bar"


async def test_transport_shipment_service_ship_commit_audit_is_not_idempotent(session: AsyncSession) -> None:
    """
    当前 Shipment 审计合同（Phase 1）：

    - ship_commit_audit 只负责写审计事件（OUTBOUND / SHIP_COMMIT），不碰库存；
    - 每次调用都会写一条审计记录（没有幂等去重）；
    - meta 中至少包含 platform / store_code 字段。
    """
    ref = "SHIP-AUDIT-1"
    platform = "PDD"
    store_code = "STORE1"
    trace_id = "TRACE-SHIP-AUDIT-1"

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

    svc = TransportShipmentService(session)

    res1 = await svc.ship_commit_audit(
        ShipCommitAuditCommand(
            ref=ref,
            platform=platform,
            store_code=store_code,
            trace_id=trace_id,
            meta={"carrier": "SF", "tracking_no": "SF123456"},
        )
    )
    assert res1.ok is True
    assert res1.ref == ref
    assert res1.trace_id == trace_id

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

    res2 = await svc.ship_commit_audit(
        ShipCommitAuditCommand(
            ref=ref,
            platform=platform,
            store_code=store_code,
            trace_id=trace_id,
            meta={"carrier": "SF", "tracking_no": "SF123456"},
        )
    )
    assert res2.ok is True
    assert res2.ref == ref
    assert res2.trace_id == trace_id

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

    if isinstance(meta_row, dict):
        assert meta_row.get("platform") == platform
        assert meta_row.get("store_code") == store_code
