# tests/services/test_audit_writer.py
from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_writer import AuditEventWriter


@pytest.fixture
async def session(async_session_maker) -> AsyncSession:
    """
    使用项目内置的 async_session_maker 构造一次性会话。
    """
    async with async_session_maker() as sess:
        yield sess


@pytest.mark.asyncio
async def test_audit_event_writer_inserts_row(session: AsyncSession):
    """
    验证 AuditEventWriter.write 能正确写入 audit_events 表，
    且 meta.flow / meta.event / trace_id 字段对齐。
    """
    flow = "OUTBOUND"
    event = "UNIT_TEST_EVENT"
    ref = "UNIT-REF-123"
    trace_id = "TRACE-UNIT-123"

    await AuditEventWriter.write(
        session,
        flow=flow,
        event=event,
        ref=ref,
        trace_id=trace_id,
        meta={"foo": "bar"},
        auto_commit=True,
    )

    row = (
        await session.execute(
            text(
                """
                SELECT category, ref, meta, trace_id
                  FROM audit_events
                 WHERE ref = :ref
                 ORDER BY id DESC
                 LIMIT 1
                """
            ),
            {"ref": ref},
        )
    ).first()

    assert row is not None
    category, ref_db, meta_db, trace_db = row
    assert category == flow
    assert ref_db == ref
    assert trace_db == trace_id

    # meta 至少要包含 flow / event / foo / trace_id
    assert isinstance(meta_db, (dict,))
    assert meta_db["flow"] == flow
    assert meta_db["event"] == event
    assert meta_db["foo"] == "bar"
    assert meta_db["trace_id"] == trace_id

    # 再简单确认一下 JSON 可序列化
    json.dumps(meta_db, ensure_ascii=False)
