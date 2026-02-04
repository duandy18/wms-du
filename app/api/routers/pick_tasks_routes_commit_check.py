# app/api/routers/pick_tasks_routes_commit_check.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.api.routers.pick_tasks_schemas import PickTaskCommitCheckOut
from app.services.pick_task_commit_check import check_commit


def register_commit_check(router: APIRouter) -> None:
    @router.get("/{task_id}/commit-check", response_model=PickTaskCommitCheckOut)
    async def get_pick_task_commit_check(
        task_id: int = Path(..., description="拣货任务 ID"),
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskCommitCheckOut:
        try:
            payload = await check_commit(session, task_id=int(task_id))
        except HTTPException:
            # ✅ Problem 化异常原样透传（404/409/422 等）
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise

        return PickTaskCommitCheckOut(**payload)
