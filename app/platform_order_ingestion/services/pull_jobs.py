# Module split: platform order ingestion pull-job service.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.contracts_pull_jobs import PlatformOrderPullJobCreateIn
from app.platform_order_ingestion.models.pull_job import (
    PlatformOrderPullJob,
    PlatformOrderPullJobRun,
    PlatformOrderPullJobRunLog,
)
from app.platform_order_ingestion.services.pull_job_executor_registry import (
    get_pull_job_executor,
)
from app.platform_order_ingestion.repos.pull_jobs import (
    create_pull_job,
    create_pull_job_run,
    create_pull_job_run_log,
    finish_pull_job_run,
    get_pull_job,
    get_pull_job_logs,
    get_pull_job_runs,
    list_pull_jobs,
)


class PlatformOrderPullJobServiceError(Exception):
    """平台订单采集任务服务异常。"""


class PlatformOrderPullJobService:
    async def create_job(
        self,
        session: AsyncSession,
        *,
        payload: PlatformOrderPullJobCreateIn,
        created_by: int | None = None,
    ) -> PlatformOrderPullJob:
        time_from = self._ensure_aware_utc(payload.time_from)
        time_to = self._ensure_aware_utc(payload.time_to)
        if bool(time_from) != bool(time_to):
            raise PlatformOrderPullJobServiceError("time_from and time_to must be both provided or both omitted")
        if time_from and time_to and time_to <= time_from:
            raise PlatformOrderPullJobServiceError("time_to must be greater than time_from")

        return await create_pull_job(
            session,
            platform=payload.platform,
            store_id=payload.store_id,
            job_type=payload.job_type,
            time_from=time_from,
            time_to=time_to,
            order_status=payload.order_status,
            page_size=payload.page_size,
            request_payload=payload.request_payload,
            created_by=created_by,
        )

    async def list_jobs(
        self,
        session: AsyncSession,
        *,
        platform: str | None = None,
        store_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[PlatformOrderPullJob], int]:
        return await list_pull_jobs(
            session,
            platform=platform,
            store_id=store_id,
            status=status,
            limit=max(1, min(int(limit), 200)),
            offset=max(0, int(offset)),
        )

    async def get_job_detail(
        self,
        session: AsyncSession,
        *,
        job_id: int,
    ) -> tuple[PlatformOrderPullJob, Sequence[PlatformOrderPullJobRun], Sequence[PlatformOrderPullJobRunLog]]:
        job = await get_pull_job(session, job_id=job_id)
        if job is None:
            raise PlatformOrderPullJobServiceError(f"platform order pull job not found: {job_id}")
        runs = await get_pull_job_runs(session, job_id=job_id)
        logs = await get_pull_job_logs(session, job_id=job_id)
        return job, runs, logs

    async def run_job_once(
        self,
        session: AsyncSession,
        *,
        job_id: int,
        page: int | None = None,
    ) -> tuple[PlatformOrderPullJob, PlatformOrderPullJobRun, Sequence[PlatformOrderPullJobRunLog]]:
        job = await get_pull_job(session, job_id=job_id)
        if job is None:
            raise PlatformOrderPullJobServiceError(f"platform order pull job not found: {job_id}")

        run_page = int(page or job.cursor_page or 1)
        if run_page <= 0:
            raise PlatformOrderPullJobServiceError("page must be positive")

        request_payload = {
            "platform": job.platform,
            "store_id": job.store_id,
            "job_id": job.id,
            "page": run_page,
            "page_size": job.page_size,
            "time_from": self._format_platform_dt(job.time_from),
            "time_to": self._format_platform_dt(job.time_to),
            "order_status": job.order_status,
        }
        run = await create_pull_job_run(
            session,
            job=job,
            page=run_page,
            request_payload=request_payload,
        )

        await create_pull_job_run_log(
            session,
            job_id=job.id,
            run_id=run.id,
            level="info",
            event_type="page_started",
            message="platform order pull page started",
            payload=request_payload,
        )

        executor = get_pull_job_executor(job.platform)
        if executor is None:
            message = f"PLATFORM_PULL_JOB_NOT_IMPLEMENTED: {job.platform}"
            await create_pull_job_run_log(
                session,
                job_id=job.id,
                run_id=run.id,
                level="error",
                event_type="page_failed",
                message=message,
                payload={"platform": job.platform},
            )
            await finish_pull_job_run(
                session,
                job=job,
                run=run,
                status="failed",
                has_more=False,
                orders_count=0,
                success_count=0,
                failed_count=0,
                result_payload=None,
                error_message=message,
            )
            logs = await get_pull_job_logs(session, job_id=job.id, run_id=run.id)
            return job, run, logs

        try:
            result = await executor.run_page(
                session=session,
                job=job,
                page=run_page,
            )
        except Exception as exc:  # noqa: BLE001 - 任务系统必须落失败记录
            message = str(exc)
            await create_pull_job_run_log(
                session,
                job_id=job.id,
                run_id=run.id,
                level="error",
                event_type="page_failed",
                message=message,
                payload=request_payload,
            )
            await finish_pull_job_run(
                session,
                job=job,
                run=run,
                status="failed",
                has_more=False,
                orders_count=0,
                success_count=0,
                failed_count=0,
                result_payload=None,
                error_message=message,
            )
            logs = await get_pull_job_logs(session, job_id=job.id, run_id=run.id)
            return job, run, logs

        for row in result.rows:
            if row.status == "OK":
                await create_pull_job_run_log(
                    session,
                    job_id=job.id,
                    run_id=run.id,
                    level="info",
                    event_type="order_ingested",
                    platform_order_no=row.platform_order_no,
                    native_order_id=row.native_order_id,
                    message=f"{result.platform} order ingested",
                    payload={"status": row.status},
                )
            else:
                await create_pull_job_run_log(
                    session,
                    job_id=job.id,
                    run_id=run.id,
                    level="error",
                    event_type="order_failed",
                    platform_order_no=row.platform_order_no,
                    native_order_id=row.native_order_id,
                    message=row.error,
                    payload={"status": row.status, "error": row.error},
                )

        run_status = self._resolve_run_status(
            orders_count=result.orders_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
        )
        result_payload = result.result_payload

        await create_pull_job_run_log(
            session,
            job_id=job.id,
            run_id=run.id,
            level="info" if run_status != "failed" else "error",
            event_type="page_finished",
            message=f"platform order pull page finished: {run_status}",
            payload=result_payload,
        )
        await finish_pull_job_run(
            session,
            job=job,
            run=run,
            status=run_status,
            has_more=result.has_more,
            orders_count=result.orders_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
            result_payload=result_payload,
            error_message=None if run_status != "failed" else "all orders failed",
        )
        logs = await get_pull_job_logs(session, job_id=job.id, run_id=run.id)
        return job, run, logs

    async def run_job_pages(
        self,
        session: AsyncSession,
        *,
        job_id: int,
        max_pages: int = 10,
    ) -> tuple[
        PlatformOrderPullJob,
        list[PlatformOrderPullJobRun],
        list[PlatformOrderPullJobRunLog],
        str,
    ]:
        max_pages_int = int(max_pages)
        if max_pages_int <= 0:
            raise PlatformOrderPullJobServiceError("max_pages must be positive")
        if max_pages_int > 100:
            raise PlatformOrderPullJobServiceError("max_pages must be <= 100")

        runs: list[PlatformOrderPullJobRun] = []
        logs: list[PlatformOrderPullJobRunLog] = []
        stopped_reason = "max_pages_reached"
        job: PlatformOrderPullJob | None = None

        for _ in range(max_pages_int):
            job, run, run_logs = await self.run_job_once(
                session,
                job_id=job_id,
                page=None,
            )
            runs.append(run)
            logs.extend(run_logs)

            if run.status == "failed":
                stopped_reason = "failed"
                break
            if not run.has_more:
                stopped_reason = "no_more"
                break

        if job is None:
            raise PlatformOrderPullJobServiceError(f"platform order pull job not found: {job_id}")

        return job, runs, logs, stopped_reason

    def _resolve_run_status(
        self,
        *,
        orders_count: int,
        success_count: int,
        failed_count: int,
    ) -> str:
        if failed_count <= 0:
            return "success"
        if success_count > 0:
            return "partial_success"
        if orders_count == 0:
            return "success"
        return "failed"

    def _ensure_aware_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _format_platform_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self._ensure_aware_utc(value).strftime("%Y-%m-%d %H:%M:%S")
