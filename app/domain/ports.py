# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class EventLogPort(Protocol):
    async def log(
        self,
        session: AsyncSession,
        *,
        source: str,
        message: str,
        occurred_at: datetime,
    ) -> int: ...
