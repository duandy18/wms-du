# tests/contracts/test_event_to_ledger_contract.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_event_to_ledger_appears_within_2s(session: AsyncSession):
    """
    事件落地：将 message 写 JSONB，2 秒内能查询到日志。
    """
    now = datetime.now(UTC)
    payload = "EVENT-LEDGER-CONTRACT"

    await session.execute(
        text(
            """
            INSERT INTO event_log(source, level, message, meta, created_at)
            VALUES ('adapter','INFO', to_jsonb(CAST(:msg AS text)), '{}'::jsonb, :ts)
        """
        ),
        {"msg": payload, "ts": now},
    )
    await session.commit()

    # 轮询 <= 2s
    ok = False
    for _ in range(10):
        row = await session.execute(
            text(
                """
                SELECT COUNT(*) FROM event_log
                 WHERE message = to_jsonb(CAST(:msg AS text))
            """
            ),
            {"msg": payload},
        )
        if int(row.scalar_one()) >= 1:
            ok = True
            break
        await asyncio.sleep(0.2)

    assert ok is True
