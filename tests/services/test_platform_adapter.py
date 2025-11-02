import pytest

pytestmark = pytest.mark.grp_events

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_event_error_log_write(session):
    """错误出口可写，最小接口有效。"""
    await session.execute(
        text(
            """
        INSERT INTO event_error_log(dedup_key, stage, error, occurred_at, meta)
        VALUES ('test:ingest:001','ingest','demo error', now(), '{}'::jsonb)
    """
        )
    )
    cnt = (
        await session.execute(
            text(
                """
        SELECT COUNT(*) FROM event_error_log WHERE dedup_key='test:ingest:001'
    """
            )
        )
    ).scalar_one()
    assert cnt >= 1
