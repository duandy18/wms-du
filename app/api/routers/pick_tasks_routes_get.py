# app/api/routers/pick_tasks_routes_get.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.api.routers.pick_tasks_helpers import load_task_with_lines
from app.api.routers.pick_tasks_schemas import PickTaskOut
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job


def register_get(router: APIRouter) -> None:
    @router.get("/{task_id}", response_model=PickTaskOut)
    async def get_pick_task(
        task_id: int = Path(..., description="拣货任务 ID"),
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        task = await load_task_with_lines(session, task_id)
        out = PickTaskOut.model_validate(task)
        out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
        return out
