# Module split: platform order ingestion pull-job repository.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform_order_ingestion.models.pull_job import (
    PlatformOrderPullJob,
    PlatformOrderPullJobRun,
    PlatformOrderPullJobRunLog,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_pull_job(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    job_type: str,
    time_from: datetime | None,
    time_to: datetime | None,
    order_status: int | None,
    page_size: int,
    request_payload: dict[str, Any] | None,
    created_by: int | None = None,
) -> PlatformOrderPullJob:
    now = utcnow()
    job = PlatformOrderPullJob(
        platform=str(platform).strip().lower(),
        store_id=int(store_id),
        job_type=str(job_type).strip().lower(),
        status="pending",
        time_from=time_from,
        time_to=time_to,
        order_status=order_status,
        page_size=int(page_size),
        cursor_page=1,
        request_payload=request_payload,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    return job


async def get_pull_job(
    session: AsyncSession,
    *,
    job_id: int,
) -> PlatformOrderPullJob | None:
    result = await session.execute(
        select(PlatformOrderPullJob)
        .where(PlatformOrderPullJob.id == int(job_id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_pull_jobs(
    session: AsyncSession,
    *,
    platform: str | None = None,
    store_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[PlatformOrderPullJob], int]:
    conditions = []
    if platform:
        conditions.append(PlatformOrderPullJob.platform == str(platform).strip().lower())
    if store_id is not None:
        conditions.append(PlatformOrderPullJob.store_id == int(store_id))
    if status:
        conditions.append(PlatformOrderPullJob.status == str(status).strip().lower())

    stmt: Select[tuple[PlatformOrderPullJob]] = select(PlatformOrderPullJob)
    count_stmt = select(func.count()).select_from(PlatformOrderPullJob)
    for cond in conditions:
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    stmt = stmt.order_by(PlatformOrderPullJob.id.desc()).limit(int(limit)).offset(int(offset))

    rows_result = await session.execute(stmt)
    total_result = await session.execute(count_stmt)
    return list(rows_result.scalars().all()), int(total_result.scalar_one() or 0)


async def create_pull_job_run(
    session: AsyncSession,
    *,
    job: PlatformOrderPullJob,
    page: int,
    request_payload: dict[str, Any] | None,
) -> PlatformOrderPullJobRun:
    now = utcnow()
    run = PlatformOrderPullJobRun(
        job_id=int(job.id),
        platform=str(job.platform),
        store_id=int(job.store_id),
        status="running",
        page=int(page),
        page_size=int(job.page_size),
        has_more=False,
        started_at=now,
        orders_count=0,
        success_count=0,
        failed_count=0,
        request_payload=request_payload,
        created_at=now,
    )
    job.status = "running"
    job.last_run_at = now
    job.updated_at = now
    session.add(run)
    await session.flush()
    return run


async def finish_pull_job_run(
    session: AsyncSession,
    *,
    job: PlatformOrderPullJob,
    run: PlatformOrderPullJobRun,
    status: str,
    has_more: bool,
    orders_count: int,
    success_count: int,
    failed_count: int,
    result_payload: dict[str, Any] | None,
    error_message: str | None = None,
) -> PlatformOrderPullJobRun:
    now = utcnow()

    run.status = str(status)
    run.has_more = bool(has_more)
    run.orders_count = int(orders_count)
    run.success_count = int(success_count)
    run.failed_count = int(failed_count)
    run.result_payload = result_payload
    run.error_message = error_message
    run.finished_at = now

    job.status = str(status)
    job.cursor_page = int(run.page) + 1 if has_more else int(run.page)
    job.last_run_at = now
    job.updated_at = now
    if status in {"success", "partial_success"}:
        job.last_success_at = now
        job.last_error_message = None
    if status == "failed":
        job.last_error_at = now
        job.last_error_message = error_message

    await session.flush()
    return run


async def create_pull_job_run_log(
    session: AsyncSession,
    *,
    job_id: int,
    run_id: int,
    level: str,
    event_type: str,
    platform_order_no: str | None = None,
    native_order_id: int | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> PlatformOrderPullJobRunLog:
    log = PlatformOrderPullJobRunLog(
        job_id=int(job_id),
        run_id=int(run_id),
        level=str(level).strip().lower(),
        event_type=str(event_type).strip(),
        platform_order_no=platform_order_no,
        native_order_id=native_order_id,
        message=message,
        payload=payload,
        created_at=utcnow(),
    )
    session.add(log)
    await session.flush()
    return log


async def get_pull_job_runs(
    session: AsyncSession,
    *,
    job_id: int,
) -> Sequence[PlatformOrderPullJobRun]:
    result = await session.execute(
        select(PlatformOrderPullJobRun)
        .where(PlatformOrderPullJobRun.job_id == int(job_id))
        .order_by(PlatformOrderPullJobRun.id.desc())
    )
    return list(result.scalars().all())


async def get_pull_job_logs(
    session: AsyncSession,
    *,
    job_id: int,
    run_id: int | None = None,
) -> Sequence[PlatformOrderPullJobRunLog]:
    stmt = select(PlatformOrderPullJobRunLog).where(PlatformOrderPullJobRunLog.job_id == int(job_id))
    if run_id is not None:
        stmt = stmt.where(PlatformOrderPullJobRunLog.run_id == int(run_id))
    result = await session.execute(stmt.order_by(PlatformOrderPullJobRunLog.id.asc()))
    return list(result.scalars().all())


async def get_pull_job_with_runs(
    session: AsyncSession,
    *,
    job_id: int,
) -> PlatformOrderPullJob | None:
    result = await session.execute(
        select(PlatformOrderPullJob)
        .options(selectinload(PlatformOrderPullJob.runs))
        .where(PlatformOrderPullJob.id == int(job_id))
        .limit(1)
    )
    return result.scalar_one_or_none()
