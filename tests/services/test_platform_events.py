import pytest

pytestmark = pytest.mark.grp_events

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_platform_events_dedup(session):
    """同一 dedup_key 只保留一条（DB 级去重）。"""
    platform = "PDD"
    event_type = "ORDER_PAID"
    event_id = str(uuid.uuid4())
    occurred_at = datetime.now(timezone.utc)
    payload = '{"demo":true}'

    # 第一次写入
    await session.execute(
        text(
            """
        INSERT INTO platform_events(platform, event_type, event_id, occurred_at, payload)
        VALUES (:p, :t, :id, :ts, :pl)
        ON CONFLICT ON CONSTRAINT uq_platform_events_dedup DO NOTHING
    """
        ),
        {"p": platform, "t": event_type, "id": event_id, "ts": occurred_at, "pl": payload},
    )

    # 再次写入（应被 DO NOTHING 吃掉）
    await session.execute(
        text(
            """
        INSERT INTO platform_events(platform, event_type, event_id, occurred_at, payload)
        VALUES (:p, :t, :id, :ts, :pl)
        ON CONFLICT ON CONSTRAINT uq_platform_events_dedup DO NOTHING
    """
        ),
        {"p": platform, "t": event_type, "id": event_id, "ts": occurred_at, "pl": payload},
    )

    # 断言只有一条
    rows = (
        await session.execute(
            text(
                """
        SELECT COUNT(*) FROM platform_events
        WHERE platform=:p AND event_type=:t AND event_id=:id
    """
            ),
            {"p": platform, "t": event_type, "id": event_id},
        )
    ).scalar_one()
    assert rows == 1
