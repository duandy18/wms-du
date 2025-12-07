# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports import EventLogPort


class EventLogAdapter(EventLogPort):
    async def log(
        self,
        session: AsyncSession,
        *,
        source: str,
        message: str,
        occurred_at: datetime,
    ) -> int:
        row = await session.execute(
            text(
                "INSERT INTO event_log(source, message, occurred_at) "
                "VALUES (:s, :m, :t) RETURNING id"
            ),
            {"s": source, "m": message, "t": occurred_at},
        )
        return int(row.scalar_one())
