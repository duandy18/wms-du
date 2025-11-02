import pytest
pytestmark = pytest.mark.grp_events

from datetime import datetime, timezone
import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_event_log_write_and_read(session):
    """写入一条轻审计日志并读回。"""
    now = datetime.now(timezone.utc)
    await session.execute(text("""
        INSERT INTO event_log(source, level, message, meta, created_at)
        VALUES ('adapter', 'INFO', 'smoke', '{}'::jsonb, :now)
    """), {"now": now})

    row = (await session.execute(text("""
        SELECT source, level, message
        FROM event_log
        ORDER BY id DESC LIMIT 1
    """))).first()
    assert row is not None and row[0] == 'adapter'
