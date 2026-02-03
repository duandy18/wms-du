# app/api/routers/pick_tasks_routes_list.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.pick_task import PickTask
from app.api.routers.pick_tasks_schemas import PickTaskOut


def register_list(router: APIRouter) -> None:
    @router.get("", response_model=List[PickTaskOut])
    async def list_pick_tasks(
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        session: AsyncSession = Depends(get_session),
    ) -> List[PickTaskOut]:
        stmt = select(PickTask).options(selectinload(PickTask.lines))

        if warehouse_id is not None:
            stmt = stmt.where(PickTask.warehouse_id == warehouse_id)

        if status is not None:
            stmt = stmt.where(PickTask.status == status)

        stmt = stmt.order_by(PickTask.priority.asc(), PickTask.id.desc()).limit(limit)

        res = await session.execute(stmt)
        tasks = res.scalars().all()

        return [PickTaskOut.model_validate(t) for t in tasks]
