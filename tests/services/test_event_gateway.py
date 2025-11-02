import pytest
pytestmark = pytest.mark.grp_events

from datetime import datetime, timezone
import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_event_replay_cursor_upsert(session):
    """回放游标存在即更新，不存在则插入。"""
    platform = 'PDD'
    ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ts2 = datetime(2025, 1, 2, tzinfo=timezone.utc)

    # 插入或忽略
    await session.execute(text("""
        INSERT INTO event_replay_cursor(platform, last_event_ts)
        VALUES (:p, :ts)
        ON CONFLICT (platform) DO UPDATE SET last_event_ts = EXCLUDED.last_event_ts
    """), {"p": platform, "ts": ts1})

    # 更新到更晚时间
    await session.execute(text("""
        INSERT INTO event_replay_cursor(platform, last_event_ts)
        VALUES (:p, :ts)
        ON CONFLICT (platform) DO UPDATE SET last_event_ts = EXCLUDED.last_event_ts
    """), {"p": platform, "ts": ts2})

    got = (await session.execute(text("""
        SELECT last_event_ts FROM event_replay_cursor WHERE platform=:p
    """), {"p": platform})).scalar_one()
    assert got == ts2
