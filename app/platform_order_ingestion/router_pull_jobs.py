# Module split: platform order ingestion pull-job API routes.
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.permissions import (
    require_platform_order_ingestion_read,
    require_platform_order_ingestion_write,
)
from app.user.deps.auth import get_current_user
from app.platform_order_ingestion.contracts_pull_jobs import (
    PlatformOrderPullJobCreateIn,
    PlatformOrderPullJobDetailDataOut,
    PlatformOrderPullJobDetailEnvelopeOut,
    PlatformOrderPullJobEnvelopeOut,
    PlatformOrderPullJobListDataOut,
    PlatformOrderPullJobListEnvelopeOut,
    PlatformOrderPullJobOut,
    PlatformOrderPullJobRunCreateIn,
    PlatformOrderPullJobRunDataOut,
    PlatformOrderPullJobRunEnvelopeOut,
    PlatformOrderPullJobRunLogOut,
    PlatformOrderPullJobRunPagesCreateIn,
    PlatformOrderPullJobRunPagesDataOut,
    PlatformOrderPullJobRunPagesEnvelopeOut,
    PlatformOrderPullJobRunOut,
)
from app.platform_order_ingestion.models.pull_job import (
    PlatformOrderPullJob,
    PlatformOrderPullJobRun,
    PlatformOrderPullJobRunLog,
)
from app.platform_order_ingestion.services.pull_jobs import (
    PlatformOrderPullJobService,
    PlatformOrderPullJobServiceError,
)

router = APIRouter(tags=["platform-order-ingestion-pull-jobs"])


def _dt(value) -> str | None:
    return value.isoformat() if value else None


def _job_out(row: PlatformOrderPullJob) -> PlatformOrderPullJobOut:
    return PlatformOrderPullJobOut(
        id=int(row.id),
        platform=row.platform,
        store_id=int(row.store_id),
        job_type=row.job_type,
        status=row.status,
        time_from=_dt(row.time_from),
        time_to=_dt(row.time_to),
        order_status=row.order_status,
        page_size=int(row.page_size),
        cursor_page=int(row.cursor_page),
        request_payload=row.request_payload,
        created_by=row.created_by,
        last_run_at=_dt(row.last_run_at),
        last_success_at=_dt(row.last_success_at),
        last_error_at=_dt(row.last_error_at),
        last_error_message=row.last_error_message,
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
    )


def _run_out(row: PlatformOrderPullJobRun) -> PlatformOrderPullJobRunOut:
    return PlatformOrderPullJobRunOut(
        id=int(row.id),
        job_id=int(row.job_id),
        platform=row.platform,
        store_id=int(row.store_id),
        status=row.status,
        page=int(row.page),
        page_size=int(row.page_size),
        has_more=bool(row.has_more),
        started_at=_dt(row.started_at),
        finished_at=_dt(row.finished_at),
        orders_count=int(row.orders_count),
        success_count=int(row.success_count),
        failed_count=int(row.failed_count),
        request_payload=row.request_payload,
        result_payload=row.result_payload,
        error_message=row.error_message,
        created_at=_dt(row.created_at),
    )


def _log_out(row: PlatformOrderPullJobRunLog) -> PlatformOrderPullJobRunLogOut:
    return PlatformOrderPullJobRunLogOut(
        id=int(row.id),
        job_id=int(row.job_id),
        run_id=int(row.run_id),
        level=row.level,
        event_type=row.event_type,
        platform_order_no=row.platform_order_no,
        native_order_id=row.native_order_id,
        message=row.message,
        payload=row.payload,
        created_at=_dt(row.created_at),
    )


@router.post(
    "/platform-order-ingestion/pull-jobs",
    response_model=PlatformOrderPullJobEnvelopeOut,
    summary="创建平台订单采集任务",
)
async def create_platform_order_pull_job(
    payload: PlatformOrderPullJobCreateIn = Body(...),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PlatformOrderPullJobEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    try:
        service = PlatformOrderPullJobService()
        job = await service.create_job(session, payload=payload)
        await session.commit()
    except PlatformOrderPullJobServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"failed to create platform order pull job: {exc}") from exc

    return PlatformOrderPullJobEnvelopeOut(ok=True, data=_job_out(job))


@router.get(
    "/platform-order-ingestion/pull-jobs",
    response_model=PlatformOrderPullJobListEnvelopeOut,
    summary="查询平台订单采集任务列表",
)
async def list_platform_order_pull_jobs(
    platform: str | None = Query(default=None),
    store_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, gt=0, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PlatformOrderPullJobListEnvelopeOut:
    require_platform_order_ingestion_read(db, current_user)

    service = PlatformOrderPullJobService()
    rows, total = await service.list_jobs(
        session,
        platform=platform,
        store_id=store_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return PlatformOrderPullJobListEnvelopeOut(
        ok=True,
        data=PlatformOrderPullJobListDataOut(
            rows=[_job_out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.get(
    "/platform-order-ingestion/pull-jobs/{job_id}",
    response_model=PlatformOrderPullJobDetailEnvelopeOut,
    summary="查询平台订单采集任务详情",
)
async def get_platform_order_pull_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PlatformOrderPullJobDetailEnvelopeOut:
    require_platform_order_ingestion_read(db, current_user)

    try:
        service = PlatformOrderPullJobService()
        job, runs, logs = await service.get_job_detail(session, job_id=job_id)
    except PlatformOrderPullJobServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PlatformOrderPullJobDetailEnvelopeOut(
        ok=True,
        data=PlatformOrderPullJobDetailDataOut(
            job=_job_out(job),
            runs=[_run_out(row) for row in runs],
            logs=[_log_out(row) for row in logs],
        ),
    )


@router.post(
    "/platform-order-ingestion/pull-jobs/{job_id}/runs",
    response_model=PlatformOrderPullJobRunEnvelopeOut,
    summary="同步执行一次平台订单采集任务",
)
async def run_platform_order_pull_job_once(
    job_id: int,
    payload: PlatformOrderPullJobRunCreateIn = Body(default_factory=PlatformOrderPullJobRunCreateIn),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PlatformOrderPullJobRunEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    try:
        service = PlatformOrderPullJobService()
        job, run, logs = await service.run_job_once(session, job_id=job_id, page=payload.page)
        await session.commit()
    except PlatformOrderPullJobServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"failed to run platform order pull job: {exc}") from exc

    return PlatformOrderPullJobRunEnvelopeOut(
        ok=True,
        data=PlatformOrderPullJobRunDataOut(
            job=_job_out(job),
            run=_run_out(run),
            logs=[_log_out(row) for row in logs],
        ),
    )

@router.post(
    "/platform-order-ingestion/pull-jobs/{job_id}/run-pages",
    response_model=PlatformOrderPullJobRunPagesEnvelopeOut,
    summary="连续执行平台订单采集任务页面",
)
async def run_platform_order_pull_job_pages(
    job_id: int,
    payload: PlatformOrderPullJobRunPagesCreateIn = Body(
        default_factory=PlatformOrderPullJobRunPagesCreateIn
    ),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PlatformOrderPullJobRunPagesEnvelopeOut:
    require_platform_order_ingestion_write(db, current_user)

    try:
        service = PlatformOrderPullJobService()
        job, runs, logs, stopped_reason = await service.run_job_pages(
            session,
            job_id=job_id,
            max_pages=payload.max_pages,
        )
        await session.commit()
    except PlatformOrderPullJobServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"failed to run platform order pull job pages: {exc}",
        ) from exc

    return PlatformOrderPullJobRunPagesEnvelopeOut(
        ok=True,
        data=PlatformOrderPullJobRunPagesDataOut(
            job=_job_out(job),
            runs=[_run_out(row) for row in runs],
            logs=[_log_out(row) for row in logs],
            pages_executed=len(runs),
            stopped_reason=stopped_reason,
        ),
    )
