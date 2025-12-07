# tests/services/test_audit_logger.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


@pytest.mark.asyncio
async def test_event_log_write_and_read(session: AsyncSession):
    """
    审计写入/读取：
    - message / meta 使用 JSONB 安全插入
    - 读取时在 SQL 侧断言 message 等于 to_jsonb(CAST(:msg AS text))
    """
    now = datetime.now(UTC)

    # 写入（message/meta 均为 JSONB）
    await session.execute(
        text(
            """
            INSERT INTO event_log (source, level, message, meta, created_at)
            VALUES (:src, :lvl, to_jsonb(CAST(:msg AS text)), '{}'::jsonb, :ts)
            """
        ),
        {"src": "adapter", "lvl": "INFO", "msg": "smoke", "ts": now},
    )

    # 读取 & 断言
    row = await session.execute(
        text(
            """
            SELECT source, level,
                   (message = to_jsonb(CAST(:msg AS text))) AS msg_ok,
                   jsonb_typeof(message)                    AS msg_type,
                   meta
              FROM event_log
             WHERE source=:src AND level=:lvl
             ORDER BY id DESC
             LIMIT 1
            """
        ),
        {"src": "adapter", "lvl": "INFO", "msg": "smoke"},
    )
    got = row.mappings().first()
    assert got is not None, "event_log 应写入一行"
    assert got["msg_ok"] is True, "message 应等于 to_jsonb('smoke')"
    assert got["msg_type"] == "string", "message 应为 JSON string 类型"
