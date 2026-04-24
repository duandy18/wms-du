# app/oms/platforms/pdd/service_mock.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.platforms.models.pdd_order import PddOrder, PddOrderItem
from app.oms.platforms.models.store_platform_connection import StorePlatformConnection
from app.oms.platforms.models.store_platform_credential import StorePlatformCredential

from .access_repository import (
    ConnectionUpsertInput,
    CredentialUpsertInput,
    upsert_connection_by_store_platform,
    upsert_credential_by_store_platform,
)
from .contracts import PddOrderDetail, PddOrderDetailItem
from .repo_orders import (
    replace_pdd_order_items,
    upsert_pdd_order,
)

PDD_PLATFORM = "pdd"
PddMockScenario = Literal["normal", "address_missing", "item_abnormal", "mixed"]


class PddMockServiceError(Exception):
    """PDD mock 服务异常。"""


@dataclass(frozen=True)
class PddMockAuthorizeResult:
    store_id: int
    platform: str
    access_token: str
    expires_at: str
    connection_status: str
    credential_status: str
    pull_ready: bool
    status: str
    status_reason: str


@dataclass(frozen=True)
class PddMockIngestRowResult:
    order_sn: str
    pdd_order_id: int
    scenario: str


@dataclass(frozen=True)
class PddMockIngestResult:
    store_id: int
    scenario: str
    count: int
    rows: list[PddMockIngestRowResult]


@dataclass(frozen=True)
class PddMockClearResult:
    store_id: int
    deleted_orders: int
    deleted_items: int
    deleted_connection_rows: int
    deleted_credential_rows: int


class PddMockService:
    """
    PDD mock 服务，只负责三件事：
    1) 模拟授权完成
    2) 模拟订单写入 pdd_orders / pdd_order_items
    3) 清理指定 store_id 的 mock 数据

    边界：
    - 不走真实 PDD 开放平台
    - 不走 WMS/TMS 匹配链
    - 不写头表处理状态
    """

    async def mock_authorize_store(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        granted_identity_display: str | None = None,
        access_token: str | None = None,
        expires_in_days: int = 365,
    ) -> PddMockAuthorizeResult:
        store_id_int = int(store_id)
        if store_id_int <= 0:
            raise PddMockServiceError("store_id must be positive")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=int(expires_in_days))
        token = (access_token or f"mock-pdd-token-{store_id_int}-{uuid4().hex[:12]}").strip()
        if not token:
            raise PddMockServiceError("access_token must not be empty")

        await upsert_credential_by_store_platform(
            session,
            data=CredentialUpsertInput(
                store_id=store_id_int,
                platform=PDD_PLATFORM,
                access_token=token,
                expires_at=expires_at,
                credential_type="oauth",
                refresh_token=f"mock-refresh-{uuid4().hex[:12]}",
                scope="pdd.order.list.get,pdd.order.information.get",
                raw_payload_json={
                    "source": "mock",
                    "mock": True,
                    "store_id": store_id_int,
                },
                granted_identity_type="store",
                granted_identity_value=str(store_id_int),
                granted_identity_display=(granted_identity_display or str(store_id_int)),
            ),
        )

        await upsert_connection_by_store_platform(
            session,
            data=ConnectionUpsertInput(
                store_id=store_id_int,
                platform=PDD_PLATFORM,
                auth_source="oauth",
                connection_status="connected",
                credential_status="valid",
                reauth_required=False,
                pull_ready=True,
                status="ready",
                status_reason="mock_authorized",
                last_authorized_at=now,
                last_pull_checked_at=now,
            ),
        )

        return PddMockAuthorizeResult(
            store_id=store_id_int,
            platform=PDD_PLATFORM,
            access_token=token,
            expires_at=expires_at.isoformat(),
            connection_status="connected",
            credential_status="valid",
            pull_ready=True,
            status="ready",
            status_reason="mock_authorized",
        )

    async def mock_ingest_orders(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        scenario: PddMockScenario = "mixed",
        count: int = 6,
    ) -> PddMockIngestResult:
        store_id_int = int(store_id)
        if store_id_int <= 0:
            raise PddMockServiceError("store_id must be positive")
        if int(count) <= 0:
            raise PddMockServiceError("count must be positive")

        rows: list[PddMockIngestRowResult] = []
        base_time = datetime.now(timezone.utc)

        for i in range(int(count)):
            row_scenario = self._resolve_row_scenario(
                scenario=scenario,
                index=i,
            )
            order_sn = self._build_order_sn(
                store_id=store_id_int,
                index=i,
            )
            confirm_at = base_time - timedelta(minutes=i)

            detail = self._build_mock_detail(
                order_sn=order_sn,
                scenario=row_scenario,
                index=i,
            )
            summary_raw_payload = self._build_mock_summary_payload(
                order_sn=order_sn,
                scenario=row_scenario,
                confirm_at=confirm_at,
                detail=detail,
            )

            pdd_order = await upsert_pdd_order(
                session,
                store_id=store_id_int,
                summary_raw_payload=summary_raw_payload,
                detail=detail,
                order_status=1,
                confirm_at=confirm_at,
            )
            await replace_pdd_order_items(
                session,
                pdd_order_id=int(pdd_order.id),
                order_sn=order_sn,
                detail=detail,
            )

            rows.append(
                PddMockIngestRowResult(
                    order_sn=order_sn,
                    pdd_order_id=int(pdd_order.id),
                    scenario=row_scenario,
                )
            )

        return PddMockIngestResult(
            store_id=store_id_int,
            scenario=scenario,
            count=int(count),
            rows=rows,
        )

    async def clear_mock_orders(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        clear_connection: bool = False,
        clear_credential: bool = False,
    ) -> PddMockClearResult:
        store_id_int = int(store_id)
        if store_id_int <= 0:
            raise PddMockServiceError("store_id must be positive")

        order_ids_result = await session.execute(
            select(PddOrder.id).where(PddOrder.store_id == store_id_int)
        )
        order_ids = [int(x) for x in order_ids_result.scalars().all()]

        deleted_items = 0
        if order_ids:
            delete_items_result = await session.execute(
                delete(PddOrderItem).where(PddOrderItem.pdd_order_id.in_(order_ids))
            )
            deleted_items = int(delete_items_result.rowcount or 0)

        delete_orders_result = await session.execute(
            delete(PddOrder).where(PddOrder.store_id == store_id_int)
        )
        deleted_orders = int(delete_orders_result.rowcount or 0)

        deleted_connection_rows = 0
        if clear_connection:
            delete_connection_result = await session.execute(
                delete(StorePlatformConnection).where(
                    StorePlatformConnection.store_id == store_id_int,
                    StorePlatformConnection.platform == PDD_PLATFORM,
                )
            )
            deleted_connection_rows = int(delete_connection_result.rowcount or 0)

        deleted_credential_rows = 0
        if clear_credential:
            delete_credential_result = await session.execute(
                delete(StorePlatformCredential).where(
                    StorePlatformCredential.store_id == store_id_int,
                    StorePlatformCredential.platform == PDD_PLATFORM,
                )
            )
            deleted_credential_rows = int(delete_credential_result.rowcount or 0)

        return PddMockClearResult(
            store_id=store_id_int,
            deleted_orders=deleted_orders,
            deleted_items=deleted_items,
            deleted_connection_rows=deleted_connection_rows,
            deleted_credential_rows=deleted_credential_rows,
        )

    def _resolve_row_scenario(
        self,
        *,
        scenario: PddMockScenario,
        index: int,
    ) -> str:
        if scenario != "mixed":
            return scenario

        scenarios = ["normal", "address_missing", "item_abnormal"]
        return scenarios[index % len(scenarios)]

    def _build_order_sn(
        self,
        *,
        store_id: int,
        index: int,
    ) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8].upper()
        return f"MOCKPDD{store_id}{stamp}{index:03d}{suffix}"

    def _build_mock_detail(
        self,
        *,
        order_sn: str,
        scenario: str,
        index: int,
    ) -> PddOrderDetail:
        province = "上海市"
        city = "上海市"
        town = "浦东新区"
        address = f"张江高科技园区测试路{100 + index}号"

        if scenario == "address_missing":
            town = None
            address = None

        items = self._build_mock_items(
            scenario=scenario,
            index=index,
        )

        raw_payload = {
            "source": "mock",
            "mock": True,
            "scenario": scenario,
            "store_id": index + 1,
            "order_sn": order_sn,
            "province": province,
            "city": city,
            "town": town,
            "receiver_name": f"测试用户{index + 1}",
            "receiver_phone": f"1380000{index:04d}",
            "receiver_address": address,
            "buyer_memo": f"mock buyer memo #{index + 1}",
            "remark": f"mock remark #{index + 1}",
            "item_list": [item.raw_item for item in items],
        }

        return PddOrderDetail(
            order_sn=order_sn,
            province=province,
            city=city,
            town=town,
            receiver_name_masked=f"测试用户{index + 1}",
            receiver_phone_masked=f"1380000{index:04d}",
            receiver_address_masked=address,
            buyer_memo=f"mock buyer memo #{index + 1}",
            remark=f"mock remark #{index + 1}",
            items=items,
            raw_payload=raw_payload,
        )

    def _build_mock_items(
        self,
        *,
        scenario: str,
        index: int,
    ) -> list[PddOrderDetailItem]:
        rows: list[PddOrderDetailItem] = []

        for j in range(2):
            goods_id = f"G-{index + 1}-{j + 1}"
            sku_id = f"SKU-{index + 1}-{j + 1}"
            outer_id = f"OUT-{index + 1}-{j + 1}"
            goods_name = f"拼多多测试商品{index + 1}-{j + 1}"
            goods_count = j + 1
            goods_price = 1299 + (index * 10) + (j * 100)

            if scenario == "item_abnormal" and j == 0:
                outer_id = None
                goods_price = None

            raw_item = {
                "source": "mock",
                "mock": True,
                "goods_id": goods_id,
                "sku_id": sku_id,
                "outer_id": outer_id,
                "goods_name": goods_name,
                "goods_count": goods_count,
                "goods_price": goods_price,
            }

            rows.append(
                PddOrderDetailItem(
                    goods_id=goods_id,
                    goods_name=goods_name,
                    sku_id=sku_id,
                    outer_id=outer_id,
                    goods_count=goods_count,
                    goods_price=goods_price,
                    raw_item=raw_item,
                )
            )

        return rows

    def _build_mock_summary_payload(
        self,
        *,
        order_sn: str,
        scenario: str,
        confirm_at: datetime,
        detail: PddOrderDetail,
    ) -> dict:
        return {
            "source": "mock",
            "mock": True,
            "scenario": scenario,
            "order_sn": order_sn,
            "order_status": 1,
            "confirm_time": confirm_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "receiver_name": detail.receiver_name_masked,
            "receiver_phone": detail.receiver_phone_masked,
            "province": detail.province,
            "city": detail.city,
            "town": detail.town,
            "address": detail.receiver_address_masked,
            "buyer_memo": detail.buyer_memo,
            "goods_count": sum(int(item.goods_count or 0) for item in detail.items),
            "item_list": [item.raw_item for item in detail.items],
        }
