# Module split: PDD owns its platform order pull-job executor implementation.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.models.pull_job import PlatformOrderPullJob
from app.platform_order_ingestion.pdd.service_ingest import PddOrderIngestService
from app.platform_order_ingestion.pdd.service_real_pull import PddRealPullParams
from app.platform_order_ingestion.services.pull_job_executor import (
    PlatformOrderPullJobPageResult,
    PlatformOrderPullJobPageRow,
)


class PddPullJobExecutor:
    platform = "pdd"

    async def run_page(
        self,
        *,
        session: AsyncSession,
        job: PlatformOrderPullJob,
        page: int,
    ) -> PlatformOrderPullJobPageResult:
        service = PddOrderIngestService()
        result = await service.ingest_order_page(
            session=session,
            params=PddRealPullParams(
                store_id=int(job.store_id),
                start_confirm_at=self._format_platform_dt(job.time_from),
                end_confirm_at=self._format_platform_dt(job.time_to),
                order_status=int(job.order_status or 1),
                page=int(page),
                page_size=int(job.page_size),
            ),
        )

        rows = [
            PlatformOrderPullJobPageRow(
                platform_order_no=row.order_sn,
                native_order_id=row.pdd_order_id,
                status=row.status,
                error=row.error,
            )
            for row in result.rows
        ]

        result_payload = {
            "platform": self.platform,
            "store_id": result.store_id,
            "store_code": result.store_code,
            "page": result.page,
            "page_size": result.page_size,
            "orders_count": result.orders_count,
            "success_count": result.success_count,
            "failed_count": result.failed_count,
            "has_more": result.has_more,
            "start_confirm_at": result.start_confirm_at,
            "end_confirm_at": result.end_confirm_at,
            "rows": [
                {
                    "order_sn": row.order_sn,
                    "pdd_order_id": row.pdd_order_id,
                    "status": row.status,
                    "error": row.error,
                }
                for row in result.rows
            ],
        }

        return PlatformOrderPullJobPageResult(
            platform=self.platform,
            store_id=int(result.store_id),
            page=int(result.page),
            page_size=int(result.page_size),
            orders_count=int(result.orders_count),
            success_count=int(result.success_count),
            failed_count=int(result.failed_count),
            has_more=bool(result.has_more),
            result_payload=result_payload,
            rows=rows,
        )

    def _format_platform_dt(self, value) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y-%m-%d %H:%M:%S")
