# Module split: JD platform order native ingest service.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.models.jd_order import JdOrder
from app.platform_order_ingestion.jd.repo_orders import (
    load_store_code_by_store_id_for_jd,
    replace_jd_order_items,
    upsert_jd_order,
)
from app.platform_order_ingestion.jd.service_order_detail import (
    JdOrderDetailService,
    JdOrderDetailServiceError,
)
from app.platform_order_ingestion.jd.service_real_pull import (
    JdRealPullParams,
    JdRealPullService,
    JdRealPullServiceError,
    JdOrderSummary,
)


class JdOrderIngestServiceError(Exception):
    """JD 平台订单入库服务异常。"""


@dataclass(frozen=True)
class JdOrderIngestRowResult:
    order_id: str
    jd_order_id: Optional[int]
    status: str
    error: Optional[str] = None


@dataclass(frozen=True)
class JdOrderIngestPageResult:
    store_id: int
    store_code: str
    page: int
    page_size: int
    orders_count: int
    success_count: int
    failed_count: int
    has_more: bool
    start_time: Optional[str]
    end_time: Optional[str]
    rows: list[JdOrderIngestRowResult]


class JdOrderIngestService:
    """
    JD 专表入库服务。

    职责：
    - 拉 JD 订单摘要页；
    - 逐单补详情；
    - 写入 jd_orders / jd_order_items。

    不负责：
    - OMS 地址校验；
    - OMS 商品映射；
    - 写 platform_order_lines；
    - 建内部 orders/order_items；
    - 触碰 finance。
    """

    def __init__(
        self,
        *,
        pull_service: JdRealPullService | None = None,
        detail_service: JdOrderDetailService | None = None,
    ) -> None:
        self.pull_service = pull_service or JdRealPullService()
        self.detail_service = detail_service or JdOrderDetailService()

    async def ingest_order_page(
        self,
        *,
        session: AsyncSession,
        params: JdRealPullParams,
    ) -> JdOrderIngestPageResult:
        store_id = int(params.store_id)
        if store_id <= 0:
            raise JdOrderIngestServiceError("store_id must be positive")

        try:
            store_code = await load_store_code_by_store_id_for_jd(
                session,
                store_id=store_id,
            )
        except Exception as exc:
            raise JdOrderIngestServiceError(
                f"failed to load jd store_code by store_id={store_id}: {exc}"
            ) from exc

        try:
            page_result = await self.pull_service.fetch_order_page(
                session=session,
                params=params,
            )
        except JdRealPullServiceError as exc:
            raise JdOrderIngestServiceError(f"jd pull failed: {exc}") from exc

        rows: list[JdOrderIngestRowResult] = []
        success_count = 0
        failed_count = 0

        for summary in page_result.orders:
            row = await self._ingest_one_summary(
                session=session,
                store_id=store_id,
                summary=summary,
            )
            rows.append(row)
            if row.status == "OK":
                success_count += 1
            else:
                failed_count += 1

        return JdOrderIngestPageResult(
            store_id=store_id,
            store_code=store_code,
            page=int(page_result.page),
            page_size=int(page_result.page_size),
            orders_count=int(page_result.orders_count),
            success_count=success_count,
            failed_count=failed_count,
            has_more=bool(page_result.has_more),
            start_time=page_result.start_time,
            end_time=page_result.end_time,
            rows=rows,
        )

    async def _ingest_one_summary(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        summary: JdOrderSummary,
    ) -> JdOrderIngestRowResult:
        order_id = str(summary.platform_order_id or "").strip()
        if not order_id:
            return JdOrderIngestRowResult(
                order_id="",
                jd_order_id=None,
                status="FAILED",
                error="empty platform_order_id",
            )

        try:
            detail = await self.detail_service.fetch_order_detail(
                session=session,
                store_id=store_id,
                order_id=order_id,
            )
            jd_order: JdOrder = await upsert_jd_order(
                session,
                store_id=store_id,
                summary=summary,
                detail=detail,
            )
            await replace_jd_order_items(
                session,
                jd_order_id=int(jd_order.id),
                order_id=order_id,
                detail=detail,
            )
            return JdOrderIngestRowResult(
                order_id=order_id,
                jd_order_id=int(jd_order.id),
                status="OK",
                error=None,
            )
        except JdOrderDetailServiceError as exc:
            return JdOrderIngestRowResult(
                order_id=order_id,
                jd_order_id=None,
                status="FAILED",
                error=f"detail_failed: {exc}",
            )
        except Exception as exc:
            return JdOrderIngestRowResult(
                order_id=order_id,
                jd_order_id=None,
                status="FAILED",
                error=str(exc),
            )
