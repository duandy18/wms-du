# Module split: platform order ingestion pull-job executor contract.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.models.pull_job import PlatformOrderPullJob


@dataclass(frozen=True)
class PlatformOrderPullJobPageRow:
    platform_order_no: str
    native_order_id: int | None
    status: str
    error: str | None = None


@dataclass(frozen=True)
class PlatformOrderPullJobPageResult:
    platform: str
    store_id: int
    page: int
    page_size: int
    orders_count: int
    success_count: int
    failed_count: int
    has_more: bool
    result_payload: dict[str, Any]
    rows: list[PlatformOrderPullJobPageRow]


class PlatformOrderPullJobExecutor(Protocol):
    platform: str

    async def run_page(
        self,
        *,
        session: AsyncSession,
        job: PlatformOrderPullJob,
        page: int,
    ) -> PlatformOrderPullJobPageResult:
        ...
