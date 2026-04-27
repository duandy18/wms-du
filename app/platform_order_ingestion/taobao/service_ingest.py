# Module split: Taobao platform order native ingest service.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.models.taobao_order import TaobaoOrder
from app.platform_order_ingestion.taobao.repo_orders import (
    load_store_code_by_store_id_for_taobao,
    replace_taobao_order_items,
    upsert_taobao_order,
)
from app.platform_order_ingestion.taobao.service_order_detail import (
    TaobaoOrderDetailService,
    TaobaoOrderDetailServiceError,
)
from app.platform_order_ingestion.taobao.service_real_pull import (
    TaobaoOrderSummary,
    TaobaoRealPullParams,
    TaobaoRealPullService,
    TaobaoRealPullServiceError,
)


class TaobaoOrderIngestServiceError(Exception):
    """淘宝平台订单入库服务异常。"""


@dataclass(frozen=True)
class TaobaoOrderIngestRowResult:
    tid: str
    taobao_order_id: Optional[int]
    status: str
    error: Optional[str] = None


@dataclass(frozen=True)
class TaobaoOrderIngestPageResult:
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
    rows: list[TaobaoOrderIngestRowResult]


class TaobaoOrderIngestService:
    """
    淘宝专表入库服务。

    职责：
    - 拉淘宝订单摘要页；
    - 逐单补详情；
    - 写入 taobao_orders / taobao_order_items。

    不负责：
    - OMS 地址校验；
    - OMS 商品映射；
    - 不写 platform_order_lines；
    - 建内部 orders/order_items；
    - 触碰 finance。
    """

    def __init__(
        self,
        *,
        pull_service: TaobaoRealPullService | None = None,
        detail_service: TaobaoOrderDetailService | None = None,
    ) -> None:
        self.pull_service = pull_service or TaobaoRealPullService()
        self.detail_service = detail_service or TaobaoOrderDetailService()

    async def ingest_order_page(
        self,
        *,
        session: AsyncSession,
        params: TaobaoRealPullParams,
    ) -> TaobaoOrderIngestPageResult:
        store_id = int(params.store_id)
        if store_id <= 0:
            raise TaobaoOrderIngestServiceError("store_id must be positive")

        try:
            store_code = await load_store_code_by_store_id_for_taobao(
                session,
                store_id=store_id,
            )
        except Exception as exc:
            raise TaobaoOrderIngestServiceError(
                f"failed to load taobao store_code by store_id={store_id}: {exc}"
            ) from exc

        try:
            page_result = await self.pull_service.fetch_order_page(
                session=session,
                params=params,
            )
        except TaobaoRealPullServiceError as exc:
            raise TaobaoOrderIngestServiceError(f"taobao pull failed: {exc}") from exc

        rows: list[TaobaoOrderIngestRowResult] = []
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

        return TaobaoOrderIngestPageResult(
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
        summary: TaobaoOrderSummary,
    ) -> TaobaoOrderIngestRowResult:
        tid = str(summary.tid or "").strip()
        if not tid:
            return TaobaoOrderIngestRowResult(
                tid="",
                taobao_order_id=None,
                status="FAILED",
                error="empty tid",
            )

        try:
            detail = await self.detail_service.fetch_order_detail(
                session=session,
                store_id=store_id,
                tid=tid,
            )
            taobao_order: TaobaoOrder = await upsert_taobao_order(
                session,
                store_id=store_id,
                summary=summary,
                detail=detail,
            )
            await replace_taobao_order_items(
                session,
                taobao_order_id=int(taobao_order.id),
                tid=tid,
                detail=detail,
            )
            return TaobaoOrderIngestRowResult(
                tid=tid,
                taobao_order_id=int(taobao_order.id),
                status="OK",
                error=None,
            )
        except TaobaoOrderDetailServiceError as exc:
            return TaobaoOrderIngestRowResult(
                tid=tid,
                taobao_order_id=None,
                status="FAILED",
                error=f"detail_failed: {exc}",
            )
        except Exception as exc:
            return TaobaoOrderIngestRowResult(
                tid=tid,
                taobao_order_id=None,
                status="FAILED",
                error=str(exc),
            )
