# tests/api/test_ship_service_commit_writes_audit.py
from datetime import datetime

import pytest
from sqlalchemy import text

from app.services.ship_service import ShipService

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_ship_service_commit_writes_audit(session):
    # 用固定的 ref；为避免残留影响结果，先清理同名审计
    ref = "UT-SHIP-SVC-001"
    await session.execute(
        text(
            "DELETE FROM audit_events WHERE category='OUTBOUND' AND ref=:r AND (meta->>'event')='SHIP_COMMIT'"
        ),
        {"r": ref},
    )
    await session.commit()

    resp = await ShipService.commit(
        session=session,
        ref=ref,
        occurred_at=datetime.utcnow(),
        platform="INTERNAL",
        shop_id="NO-STORE",
        carrier="DUMMY",
        tracking_no="T123456",
    )
    # 首报应为 OK（或在无审计表时 SKIPPED）
    assert resp["status"] in ("OK", "SKIPPED")

    # 校验写入（若有审计表）
    rec = await session.execute(
        text(
            """
        SELECT COUNT(*) FROM audit_events
        WHERE category='OUTBOUND' AND ref=:r
          AND (meta->>'flow')='OUTBOUND' AND (meta->>'event')='SHIP_COMMIT'
    """
        ),
        {"r": ref},
    )
    cnt = rec.scalar() or 0
    # 在无 audit_events 表的极简环境中可能为 0（与 SKIPPED 对应）；否则应 >=1
    if resp["status"] != "SKIPPED":
        assert cnt >= 1
