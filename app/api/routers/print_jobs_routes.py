# app/api/routers/print_jobs_routes.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.db.session import get_session
from app.services.print_jobs_service import load_print_job, mark_print_job_failed, mark_print_job_printed


class MarkPrintedIn(BaseModel):
    printed_at: Optional[datetime] = Field(default=None, description="打印完成时间；不传则后端取 now()")


class MarkFailedIn(BaseModel):
    error: str = Field(..., min_length=1, max_length=2000, description="失败原因（可直接展示给操作员）")


def register(router: APIRouter) -> None:
    @router.get("/{job_id}")
    async def get_print_job(job_id: int, session: AsyncSession = Depends(get_session)) -> Dict[str, Any]:
        job = await load_print_job(session, job_id=int(job_id))
        if not job:
            raise_problem(
                status_code=404,
                error_code="print_job_not_found",
                message="打印任务不存在。",
                context={"job_id": int(job_id)},
                details=[{"type": "resource", "path": "job_id", "reason": "not_found"}],
                next_actions=[{"action": "refresh", "label": "刷新"}],
            )
        return {"status": "OK", "job": job}

    @router.post("/{job_id}/printed")
    async def mark_printed(
        job_id: int,
        body: MarkPrintedIn,
        session: AsyncSession = Depends(get_session),
    ) -> Dict[str, Any]:
        job = await load_print_job(session, job_id=int(job_id))
        if not job:
            raise_problem(
                status_code=404,
                error_code="print_job_not_found",
                message="打印任务不存在。",
                context={"job_id": int(job_id)},
                details=[{"type": "resource", "path": "job_id", "reason": "not_found"}],
                next_actions=[{"action": "refresh", "label": "刷新"}],
            )

        try:
            await mark_print_job_printed(session, job_id=int(job_id), printed_at=body.printed_at)
            # ✅ 合同：请求返回 200 时数据库状态必须可见
            await session.commit()
        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            raise_problem(
                status_code=500,
                error_code="print_job_update_failed",
                message="打印任务回写失败：系统异常。",
                context={"job_id": int(job_id)},
                details=[{"type": "state", "path": "mark_printed", "reason": str(e)}],
            )

        job2 = await load_print_job(session, job_id=int(job_id))
        return {"status": "OK", "job": job2}

    @router.post("/{job_id}/failed")
    async def mark_failed(
        job_id: int,
        body: MarkFailedIn,
        session: AsyncSession = Depends(get_session),
    ) -> Dict[str, Any]:
        job = await load_print_job(session, job_id=int(job_id))
        if not job:
            raise_problem(
                status_code=404,
                error_code="print_job_not_found",
                message="打印任务不存在。",
                context={"job_id": int(job_id)},
                details=[{"type": "resource", "path": "job_id", "reason": "not_found"}],
                next_actions=[{"action": "refresh", "label": "刷新"}],
            )

        err = (body.error or "").strip()
        if not err:
            raise_problem(
                status_code=422,
                error_code="invalid_error",
                message="失败原因不能为空。",
                context={"job_id": int(job_id)},
                details=[{"type": "validation", "path": "error", "reason": "empty"}],
            )

        try:
            await mark_print_job_failed(session, job_id=int(job_id), error=err)
            # ✅ 合同：请求返回 200 时数据库状态必须可见
            await session.commit()
        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            raise_problem(
                status_code=500,
                error_code="print_job_update_failed",
                message="打印任务回写失败：系统异常。",
                context={"job_id": int(job_id)},
                details=[{"type": "state", "path": "mark_failed", "reason": str(e)}],
            )

        job2 = await load_print_job(session, job_id=int(job_id))
        return {"status": "OK", "job": job2}
