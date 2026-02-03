# app/api/routers/pick_tasks_routes_diff.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService
from app.api.routers.pick_tasks_schemas import PickTaskDiffLineOut, PickTaskDiffSummaryOut


def register_diff(router: APIRouter) -> None:
    @router.get("/{task_id}/diff", response_model=PickTaskDiffSummaryOut)
    async def get_pick_task_diff(
        task_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskDiffSummaryOut:
        svc = PickTaskService(session)
        try:
            summary = await svc.compute_diff(task_id=task_id)
        except ValueError as e:
            raise_problem(
                status_code=http_status.HTTP_404_NOT_FOUND,
                error_code="pick_task_not_found",
                message=str(e),
                details=[{"type": "resource", "path": "task_id", "task_id": int(task_id), "reason": "not_found"}],
            )

        lines = [
            PickTaskDiffLineOut(
                item_id=line.item_id,
                req_qty=line.req_qty,
                picked_qty=line.picked_qty,
                delta=line.delta,
                status=line.status,
            )
            for line in summary.lines
        ]

        return PickTaskDiffSummaryOut(
            task_id=summary.task_id,
            has_over=summary.has_over,
            has_under=summary.has_under,
            lines=lines,
        )
