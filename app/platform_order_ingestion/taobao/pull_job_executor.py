# Module split: Taobao owns its platform order pull-job executor implementation.
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.models.pull_job import PlatformOrderPullJob
from app.platform_order_ingestion.services.pull_job_executor import (
    PlatformOrderPullJobPageResult,
    PlatformOrderPullJobPageRow,
)
from app.platform_order_ingestion.taobao.service_ingest import TaobaoOrderIngestService
from app.platform_order_ingestion.taobao.service_real_pull import TaobaoRealPullParams


class TaobaoPullJobExecutor:
    platform = "taobao"

    async def run_page(
        self,
        *,
        session: AsyncSession,
        job: PlatformOrderPullJob,
        page: int,
    ) -> PlatformOrderPullJobPageResult:
        service = TaobaoOrderIngestService()
        result = await service.ingest_order_page(
            session=session,
            params=TaobaoRealPullParams(
                store_id=int(job.store_id),
                start_time=self._format_platform_dt(job.time_from),
                end_time=self._format_platform_dt(job.time_to),
                status=self._resolve_status(job.request_payload),
                page=int(page),
                page_size=int(job.page_size),
            ),
        )

        rows = [
            PlatformOrderPullJobPageRow(
                platform_order_no=row.tid,
                native_order_id=row.taobao_order_id,
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
            "start_time": result.start_time,
            "end_time": result.end_time,
            "rows": [
                {
                    "tid": row.tid,
                    "taobao_order_id": row.taobao_order_id,
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

    def _resolve_status(self, request_payload: dict[str, Any] | None) -> str | None:
        if not isinstance(request_payload, dict):
            return None
        value = request_payload.get("status")
        text = str(value or "").strip()
        return text or None
