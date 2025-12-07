# app/services/_event_writer.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


@dataclass
class EventRecord:
    id: int
    source: str
    level: str
    message: Any
    meta: Any
    created_at: datetime


@dataclass
class EventStoreRecord:
    id: int
    topic: str
    key: str | None
    payload: Any
    headers: Any
    status: str
    attempts: int
    occurred_at: datetime
    trace_id: str | None


class EventWriter:
    """
    事件统一写入：
    - event_log：write_json（原行为，保持不变）
    - event_store：write_store（新增，用于正式 trace 流）
    """

    def __init__(self, source: str):
        # 对于 event_store，这里会作为 topic 使用
        self.source = source

    @staticmethod
    def _jsonb_param(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False)

    async def write_json(
        self,
        session: AsyncSession,
        *,
        level: str,
        message: Any,
        meta: Optional[Mapping[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ) -> EventRecord:
        """
        写入 event_log（原有行为）：
        - source / level / message / meta / created_at
        """
        ts = created_at or datetime.now(UTC)
        q = SA(
            """
            INSERT INTO event_log (source, level, message, meta, created_at)
            VALUES (:src, :lvl, CAST(:msg AS jsonb), CAST(:meta AS jsonb), :ts)
            RETURNING id, source, level, message, meta, created_at
            """
        )
        row = await session.execute(
            q,
            {
                "src": self.source,
                "lvl": level,
                "msg": self._jsonb_param(message),
                "meta": self._jsonb_param(meta or {}),
                "ts": ts,
            },
        )
        r = row.first()
        return EventRecord(
            id=int(r.id),
            source=r.source,
            level=r.level,
            message=r.message,
            meta=r.meta,
            created_at=r.created_at,
        )

    async def write_store(
        self,
        session: AsyncSession,
        *,
        payload: Any,
        key: Optional[str] = None,
        headers: Optional[Mapping[str, Any]] = None,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> EventStoreRecord:
        """
        写入 event_store：
        - topic = self.source
        - key = 任意字符串（通常为 trace_id 或业务 ref）
        - payload = 任意 JSON 对象
        - headers = 额外元数据（可选）
        - trace_id = TraceService 聚合主键（对于 Scan 必须传）
        """
        ts = occurred_at or datetime.now(UTC)
        q = SA(
            """
            INSERT INTO event_store (topic, key, payload, headers, occurred_at, trace_id)
            VALUES (:topic, :key, CAST(:payload AS jsonb), CAST(:headers AS jsonb), :ts, :trace_id)
            RETURNING id, topic, key, payload, headers, status, attempts, occurred_at, trace_id
            """
        )
        row = await session.execute(
            q,
            {
                "topic": self.source,
                "key": key,
                "payload": self._jsonb_param(payload),
                "headers": self._jsonb_param(headers or {}),
                "ts": ts,
                "trace_id": trace_id,
            },
        )
        r = row.first()
        return EventStoreRecord(
            id=int(r.id),
            topic=r.topic,
            key=r.key,
            payload=r.payload,
            headers=r.headers,
            status=r.status,
            attempts=r.attempts,
            occurred_at=r.occurred_at,
            trace_id=r.trace_id,
        )
