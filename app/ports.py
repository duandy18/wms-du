# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class StockOpsPort(Protocol):
    async def transfer(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        src_location_id: int,
        dst_location_id: int,
        qty: int,
        reason: str,
        ref: Optional[str],
    ) -> Dict[str, Any]: ...


class EventLogPort(Protocol):
    async def log(
        self,
        session: AsyncSession,
        *,
        source: str,
        message: str,
        occurred_at: datetime,
    ) -> int: ...
