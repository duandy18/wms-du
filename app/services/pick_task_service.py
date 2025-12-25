# app/services/pick_task_service.py
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick_task import PickTask

from app.services.pick_task_commit_ship import commit_ship as _commit_ship
from app.services.pick_task_create import create_for_order as _create_for_order
from app.services.pick_task_diff import compute_diff as _compute_diff
from app.services.pick_task_loaders import load_task as _load_task
from app.services.pick_task_mark_done import mark_done as _mark_done
from app.services.pick_task_scan import record_scan as _record_scan
from app.services.pick_task_types import PickTaskCommitLine, PickTaskDiffLine, PickTaskDiffSummary
from app.services.pick_task_views import get_commit_lines as _get_commit_lines

UTC = timezone.utc


class PickTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_task(
        self,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> PickTask:
        return await _load_task(self.session, task_id, for_update=for_update)

    async def create_for_order(
        self,
        *,
        order_id: int,
        warehouse_id: Optional[int] = None,
        source: str = "ORDER",
        priority: int = 100,
    ) -> PickTask:
        return await _create_for_order(
            self.session,
            order_id=order_id,
            warehouse_id=warehouse_id,
            source=source,
            priority=priority,
        )

    async def record_scan(
        self,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str],
    ) -> PickTask:
        return await _record_scan(
            self.session,
            task_id=task_id,
            item_id=item_id,
            qty=qty,
            batch_code=batch_code,
        )

    async def get_commit_lines(
        self,
        *,
        task_id: int,
        ignore_zero: bool = True,
    ):
        return await _get_commit_lines(self.session, task_id=task_id, ignore_zero=ignore_zero)

    async def compute_diff(
        self,
        *,
        task_id: int,
    ) -> PickTaskDiffSummary:
        return await _compute_diff(self.session, task_id=task_id)

    async def commit_ship(
        self,
        *,
        task_id: int,
        platform: str,
        shop_id: str,
        trace_id: Optional[str] = None,
        allow_diff: bool = True,
    ) -> Dict[str, Any]:
        return await _commit_ship(
            self.session,
            task_id=task_id,
            platform=platform,
            shop_id=shop_id,
            trace_id=trace_id,
            allow_diff=allow_diff,
        )

    async def mark_done(
        self,
        *,
        task_id: int,
        note: Optional[str] = None,
    ) -> PickTask:
        return await _mark_done(self.session, task_id=task_id, note=note)


__all__ = [
    "UTC",
    "PickTaskCommitLine",
    "PickTaskDiffLine",
    "PickTaskDiffSummary",
    "PickTaskService",
]
