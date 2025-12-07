# tests/services/test_ship_service.py
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ship_service import ShipService


@pytest.fixture
async def session(async_session_maker) -> AsyncSession:
    """
    复用 async_session_maker 构造一次性会话。
    """
    async with async_session_maker() as sess:
        yield sess


@pytest.mark.asyncio
async def test_ship_service_commit_writes_audit(session: AsyncSession):
    """
    验证 ShipService.commit 会写一条 SHIP_COMMIT 审计事件到 audit_events。
    """
    svc = ShipService(session)
    ref = "SHIP-UNIT-001"
    platform = "PDD"
    shop_id = "1"
    trace_id = "TRACE-SHIP-001"

    result = await svc.commit(
        ref=ref,
        platform=platform,
        shop_id=shop_id,
        trace_id=trace_id,
        meta={"foo": "bar"},
    )
    assert result["ok"] is True
    assert result["ref"] == ref
    assert result["trace_id"] == trace_id

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

    assert isinstance(meta_db, (dict,))
    assert meta_db["flow"] == "OUTBOUND"
    assert meta_db["event"] == "SHIP_COMMIT"
    assert meta_db["platform"] == platform.upper()
    assert meta_db["shop_id"] == shop_id
    assert meta_db["foo"] == "bar"
