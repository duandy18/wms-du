# app/services/event_error_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


@dataclass
class LoggedError:
    id: Optional[int]
    dedup_key: str
    stage: str
    error: str


class EventErrorService:
    """
    统一错误写入 event_error_log，使用保存点隔离，不污染业务事务。
    不做字符串拼接，全部参数化。
    """

    def __init__(self, stage: str = "ingest"):
        self.stage = stage

    async def log(
        self,
        session: AsyncSession,
        *,
        dedup_key: str,
        error: str,
        meta: Optional[Mapping[str, Any]] = None,
        occurred_at: Optional[datetime] = None,
    ) -> LoggedError:
        ts = occurred_at or datetime.now(UTC)
        # 统一将 meta 映射为 jsonb：先转字符串，再在 SQL 侧 to_jsonb(text)
        meta_text = "{}" if meta is None else str(dict(meta))
        # 保存点隔离
        async with session.begin_nested():
            row = await session.execute(
                SA(
                    """
                    INSERT INTO event_error_log (dedup_key, stage, error, occurred_at, meta)
                    VALUES (:k, :stg, :err, :ts, to_jsonb(CAST(:m AS text))::jsonb)
                    RETURNING id
                """
                ),
                {"k": dedup_key, "stg": self.stage, "err": error[:240], "ts": ts, "m": meta_text},
            )
            rid = row.scalar_one()
        return LoggedError(id=int(rid), dedup_key=dedup_key, stage=self.stage, error=error[:240])
