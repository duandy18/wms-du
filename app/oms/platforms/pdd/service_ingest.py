from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.platforms.models.pdd_order import PddOrder
from app.oms.platforms.pdd.contracts import PddOrderSummary
from app.oms.platforms.pdd.repo_orders import (
    load_store_code_by_store_id_for_pdd,
    replace_pdd_order_items,
    upsert_pdd_order,
)
from app.oms.platforms.pdd.service_order_detail import (
    PddOrderDetailService,
    PddOrderDetailServiceError,
)
from app.oms.platforms.pdd.service_real_pull import (
    PddRealPullParams,
    PddRealPullService,
    PddRealPullServiceError,
)


class PddOrderIngestServiceError(Exception):
    """PDD 平台订单入库服务异常。"""


@dataclass(frozen=True)
class PddOrderIngestRowResult:
    order_sn: str
    pdd_order_id: Optional[int]
    status: str
    error: Optional[str] = None


@dataclass(frozen=True)
class PddOrderIngestPageResult:
    store_id: int
    store_code: str
    page: int
    page_size: int
    orders_count: int
    success_count: int
    failed_count: int
    has_more: bool
    start_confirm_at: Optional[str]
    end_confirm_at: Optional[str]
    rows: List[PddOrderIngestRowResult]


class PddOrderIngestService:
    """
    PDD 专表入库服务（第一版）。

    职责：
    - 拉 PDD 订单摘要页
    - 逐单补详情并解密
    - 入 pdd_orders / pdd_order_items

    不负责：
    - OMS 地址校验
    - OMS 商品映射
    - 建内部 orders
    - 写 pdd_order_order_mappings
    """

    def __init__(
        self,
        *,
        pull_service: Optional[PddRealPullService] = None,
        detail_service: Optional[PddOrderDetailService] = None,
    ) -> None:
        self.pull_service = pull_service or PddRealPullService()
        self.detail_service = detail_service or PddOrderDetailService()

    async def ingest_order_page(
        self,
        *,
        session: AsyncSession,
        params: PddRealPullParams,
    ) -> PddOrderIngestPageResult:
        store_id = int(params.store_id)
        if store_id <= 0:
            raise PddOrderIngestServiceError("store_id must be positive")

        try:
            store_code = await load_store_code_by_store_id_for_pdd(
                session,
                store_id=store_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise PddOrderIngestServiceError(
                f"failed to load pdd store_code by store_id={store_id}: {exc}"
            ) from exc

        try:
            page_result = await self.pull_service.fetch_order_page(
                session=session,
                params=params,
            )
        except PddRealPullServiceError as exc:
            raise PddOrderIngestServiceError(f"pdd pull failed: {exc}") from exc

        rows: List[PddOrderIngestRowResult] = []
        success_count = 0
        failed_count = 0

        for summary in page_result.orders:
            row = await self._ingest_one_summary(
                session=session,
                store_id=store_id,
                store_code=store_code,
                summary=summary,
            )
            rows.append(row)
            if row.status == "OK":
                success_count += 1
            else:
                failed_count += 1

        return PddOrderIngestPageResult(
            store_id=store_id,
            store_code=store_code,
            page=page_result.page,
            page_size=page_result.page_size,
            orders_count=page_result.orders_count,
            success_count=success_count,
            failed_count=failed_count,
            has_more=page_result.has_more,
            start_confirm_at=getattr(page_result, "start_confirm_at", None),
            end_confirm_at=getattr(page_result, "end_confirm_at", None),
            rows=rows,
        )

    async def _ingest_one_summary(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        store_code: str,
        summary: PddOrderSummary,
    ) -> PddOrderIngestRowResult:
        order_sn = str(summary.platform_order_id or "").strip()
        if not order_sn:
            return PddOrderIngestRowResult(
                order_sn="",
                pdd_order_id=None,
                status="FAILED",
                error="empty platform_order_id",
            )

        try:
            detail = await self.detail_service.fetch_order_detail(
                session=session,
                store_id=store_id,
                order_sn=order_sn,
            )
            confirm_at = self._parse_optional_dt(summary.confirm_at)

            pdd_order: PddOrder = await upsert_pdd_order(
                session,
                store_id=store_id,
                store_code=store_code,
                summary_raw_payload=summary.raw_order,
                detail=detail,
                order_status=summary.order_status,
                confirm_at=confirm_at,
            )

            await replace_pdd_order_items(
                session,
                pdd_order_id=int(pdd_order.id),
                order_sn=order_sn,
                detail=detail,
            )

            return PddOrderIngestRowResult(
                order_sn=order_sn,
                pdd_order_id=int(pdd_order.id),
                status="OK",
                error=None,
            )
        except PddOrderDetailServiceError as exc:
            return PddOrderIngestRowResult(
                order_sn=order_sn,
                pdd_order_id=None,
                status="FAILED",
                error=f"detail_failed: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return PddOrderIngestRowResult(
                order_sn=order_sn,
                pdd_order_id=None,
                status="FAILED",
                error=str(exc),
            )

    def _parse_optional_dt(self, value: Optional[str]) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None

        # 当前 PDD 拉单摘要时间格式按 service_real_pull 的约束处理：
        # yyyy-MM-dd HH:mm:ss，先按 naive UTC 解释。
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
