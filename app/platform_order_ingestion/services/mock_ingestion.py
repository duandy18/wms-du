# Module split: platform order ingestion unified mock service.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.jd.repo_orders import replace_jd_order_items, upsert_jd_order
from app.platform_order_ingestion.jd.service_order_detail import JdOrderDetail, JdOrderDetailItem
from app.platform_order_ingestion.jd.service_real_pull import JdOrderSummary
from app.platform_order_ingestion.models.jd_order import JdOrder, JdOrderItem
from app.platform_order_ingestion.models.pdd_order import PddOrder, PddOrderItem
from app.platform_order_ingestion.models.store_platform_connection import StorePlatformConnection
from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential
from app.platform_order_ingestion.models.taobao_order import TaobaoOrder, TaobaoOrderItem
from app.platform_order_ingestion.pdd.contracts import PddOrderDetail, PddOrderDetailItem
from app.platform_order_ingestion.pdd.repo_orders import replace_pdd_order_items, upsert_pdd_order
from app.platform_order_ingestion.taobao.repo_orders import replace_taobao_order_items, upsert_taobao_order
from app.platform_order_ingestion.taobao.service_order_detail import TaobaoOrderDetail, TaobaoOrderDetailItem
from app.platform_order_ingestion.taobao.service_real_pull import TaobaoOrderSummary

Platform = Literal["pdd", "jd", "taobao"]
Scenario = Literal["normal", "address_missing", "item_abnormal", "mixed"]


class PlatformOrderIngestionMockServiceError(Exception):
    """平台订单采集 mock 服务异常。"""


@dataclass(frozen=True)
class MockAuthorizeResult:
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
class MockIngestRowResult:
    platform_order_no: str
    native_order_id: int
    scenario: str


@dataclass(frozen=True)
class MockIngestResult:
    store_id: int
    platform: str
    scenario: str
    count: int
    rows: list[MockIngestRowResult]


@dataclass(frozen=True)
class MockClearResult:
    store_id: int
    platform: str
    deleted_orders: int
    deleted_items: int
    deleted_connection_rows: int
    deleted_credential_rows: int


class PlatformOrderIngestionMockService:
    """
    通用平台订单采集 mock 服务。

    职责：
    - 用 curl 模拟店铺授权；
    - 用 curl 模拟平台原生订单入库；
    - 清理指定店铺的 mock 数据。

    不负责：
    - 调真实平台；
    - 写 platform_order_lines；
    - FSKU / SKU 映射；
    - 内部订单创建；
    - Finance / WMS / TMS。
    """

    async def mock_authorize_store(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        platform: Platform,
        granted_identity_display: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        expires_in_days: int = 365,
        pull_ready: bool = True,
    ) -> MockAuthorizeResult:
        store_id_int = self._validate_store_id(store_id)
        platform_norm = self._validate_platform(platform)
        store = await self._load_store(session, store_id=store_id_int, platform=platform_norm)
        await self._ensure_mock_app_config(session, platform=platform_norm)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=int(expires_in_days))
        token = str(access_token or f"mock-{platform_norm}-token-{store_id_int}-{uuid4().hex[:12]}").strip()
        if not token:
            raise PlatformOrderIngestionMockServiceError("access_token must not be empty")

        refresh = str(refresh_token or f"mock-{platform_norm}-refresh-{uuid4().hex[:12]}").strip()
        display = granted_identity_display or str(store["store_code"])

        await self._upsert_credential(
            session,
            store_id=store_id_int,
            platform=platform_norm,
            access_token=token,
            refresh_token=refresh,
            expires_at=expires_at,
            granted_identity_display=display,
        )
        await self._upsert_connection(
            session,
            store_id=store_id_int,
            platform=platform_norm,
            pull_ready=bool(pull_ready),
            now=now,
        )

        return MockAuthorizeResult(
            store_id=store_id_int,
            platform=platform_norm,
            access_token=token,
            expires_at=expires_at.isoformat(),
            connection_status="connected",
            credential_status="valid",
            pull_ready=bool(pull_ready),
            status="ready" if pull_ready else "authorized",
            status_reason="mock_authorized",
        )

    async def mock_ingest_orders(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        platform: Platform,
        scenario: Scenario = "mixed",
        count: int = 6,
    ) -> MockIngestResult:
        store_id_int = self._validate_store_id(store_id)
        platform_norm = self._validate_platform(platform)
        self._validate_count(count)
        await self._load_store(session, store_id=store_id_int, platform=platform_norm)

        rows: list[MockIngestRowResult] = []
        base_time = datetime.now(timezone.utc)

        for index in range(int(count)):
            row_scenario = self._resolve_row_scenario(scenario=scenario, index=index)

            if platform_norm == "pdd":
                row = await self._mock_ingest_pdd_order(
                    session=session,
                    store_id=store_id_int,
                    scenario=row_scenario,
                    index=index,
                    base_time=base_time,
                )
            elif platform_norm == "jd":
                row = await self._mock_ingest_jd_order(
                    session=session,
                    store_id=store_id_int,
                    scenario=row_scenario,
                    index=index,
                    base_time=base_time,
                )
            elif platform_norm == "taobao":
                row = await self._mock_ingest_taobao_order(
                    session=session,
                    store_id=store_id_int,
                    scenario=row_scenario,
                    index=index,
                    base_time=base_time,
                )
            else:  # pragma: no cover
                raise PlatformOrderIngestionMockServiceError(f"unsupported platform: {platform_norm}")

            rows.append(row)

        return MockIngestResult(
            store_id=store_id_int,
            platform=platform_norm,
            scenario=scenario,
            count=int(count),
            rows=rows,
        )

    async def clear_mock_orders(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        platform: Platform,
        clear_connection: bool = False,
        clear_credential: bool = False,
    ) -> MockClearResult:
        store_id_int = self._validate_store_id(store_id)
        platform_norm = self._validate_platform(platform)
        await self._load_store(session, store_id=store_id_int, platform=platform_norm)

        deleted_orders = 0
        deleted_items = 0

        if platform_norm == "pdd":
            order_model = PddOrder
            item_model = PddOrderItem
            item_fk = PddOrderItem.pdd_order_id
        elif platform_norm == "jd":
            order_model = JdOrder
            item_model = JdOrderItem
            item_fk = JdOrderItem.jd_order_id
        elif platform_norm == "taobao":
            order_model = TaobaoOrder
            item_model = TaobaoOrderItem
            item_fk = TaobaoOrderItem.taobao_order_id
        else:  # pragma: no cover
            raise PlatformOrderIngestionMockServiceError(f"unsupported platform: {platform_norm}")

        order_ids_result = await session.execute(
            sa.select(order_model.id).where(order_model.store_id == store_id_int)
        )
        order_ids = [int(x) for x in order_ids_result.scalars().all()]

        if order_ids:
            delete_items_result = await session.execute(
                sa.delete(item_model).where(item_fk.in_(order_ids))
            )
            deleted_items = int(delete_items_result.rowcount or 0)

        delete_orders_result = await session.execute(
            sa.delete(order_model).where(order_model.store_id == store_id_int)
        )
        deleted_orders = int(delete_orders_result.rowcount or 0)

        deleted_connection_rows = 0
        if clear_connection:
            delete_connection_result = await session.execute(
                sa.delete(StorePlatformConnection).where(
                    StorePlatformConnection.store_id == store_id_int,
                    StorePlatformConnection.platform == platform_norm,
                )
            )
            deleted_connection_rows = int(delete_connection_result.rowcount or 0)

        deleted_credential_rows = 0
        if clear_credential:
            delete_credential_result = await session.execute(
                sa.delete(StorePlatformCredential).where(
                    StorePlatformCredential.store_id == store_id_int,
                    StorePlatformCredential.platform == platform_norm,
                )
            )
            deleted_credential_rows = int(delete_credential_result.rowcount or 0)

        return MockClearResult(
            store_id=store_id_int,
            platform=platform_norm,
            deleted_orders=deleted_orders,
            deleted_items=deleted_items,
            deleted_connection_rows=deleted_connection_rows,
            deleted_credential_rows=deleted_credential_rows,
        )

    async def _ensure_mock_app_config(
        self,
        session: AsyncSession,
        *,
        platform: str,
    ) -> None:
        if platform == "pdd":
            result = await session.execute(
                sa.text(
                    """
                    UPDATE pdd_app_configs
                       SET client_id = 'mock-pdd-client-id',
                           client_secret = 'mock-pdd-client-secret',
                           redirect_uri = 'http://127.0.0.1:8000/oms/pdd/oauth/callback',
                           api_base_url = 'https://gw-api.pinduoduo.com/api/router',
                           sign_method = 'md5',
                           is_enabled = TRUE
                     WHERE is_enabled IS TRUE
                    """
                )
            )
            if int(result.rowcount or 0) == 0:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO pdd_app_configs (
                          client_id,
                          client_secret,
                          redirect_uri,
                          api_base_url,
                          sign_method,
                          is_enabled
                        )
                        VALUES (
                          'mock-pdd-client-id',
                          'mock-pdd-client-secret',
                          'http://127.0.0.1:8000/oms/pdd/oauth/callback',
                          'https://gw-api.pinduoduo.com/api/router',
                          'md5',
                          TRUE
                        )
                        """
                    )
                )
            return

        if platform == "jd":
            result = await session.execute(
                sa.text(
                    """
                    UPDATE jd_app_configs
                       SET client_id = 'mock-jd-client-id',
                           client_secret = 'mock-jd-client-secret',
                           callback_url = 'http://127.0.0.1:8000/oms/jd/oauth/callback',
                           gateway_url = 'https://api.jd.com/routerjson',
                           sign_method = 'md5',
                           is_enabled = TRUE
                     WHERE is_enabled IS TRUE
                    """
                )
            )
            if int(result.rowcount or 0) == 0:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO jd_app_configs (
                          client_id,
                          client_secret,
                          callback_url,
                          gateway_url,
                          sign_method,
                          is_enabled
                        )
                        VALUES (
                          'mock-jd-client-id',
                          'mock-jd-client-secret',
                          'http://127.0.0.1:8000/oms/jd/oauth/callback',
                          'https://api.jd.com/routerjson',
                          'md5',
                          TRUE
                        )
                        """
                    )
                )
            return

        if platform == "taobao":
            result = await session.execute(
                sa.text(
                    """
                    UPDATE taobao_app_configs
                       SET app_key = 'mock-taobao-app-key',
                           app_secret = 'mock-taobao-app-secret',
                           callback_url = 'http://127.0.0.1:8000/oms/taobao/oauth/callback',
                           api_base_url = 'https://eco.taobao.com/router/rest',
                           sign_method = 'md5',
                           is_enabled = TRUE
                     WHERE is_enabled IS TRUE
                    """
                )
            )
            if int(result.rowcount or 0) == 0:
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO taobao_app_configs (
                          app_key,
                          app_secret,
                          callback_url,
                          api_base_url,
                          sign_method,
                          is_enabled
                        )
                        VALUES (
                          'mock-taobao-app-key',
                          'mock-taobao-app-secret',
                          'http://127.0.0.1:8000/oms/taobao/oauth/callback',
                          'https://eco.taobao.com/router/rest',
                          'md5',
                          TRUE
                        )
                        """
                    )
                )
            return

        raise PlatformOrderIngestionMockServiceError(f"unsupported platform: {platform}")

    async def _upsert_credential(
        self,
        session: AsyncSession,
        *,
        store_id: int,
        platform: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        granted_identity_display: str,
    ) -> StorePlatformCredential:
        row = (
            await session.execute(
                sa.select(StorePlatformCredential).where(
                    StorePlatformCredential.store_id == store_id,
                    StorePlatformCredential.platform == platform,
                )
            )
        ).scalar_one_or_none()

        scope = self._mock_scope(platform)
        raw_payload_json = {
            "source": "unified_mock",
            "mock": True,
            "store_id": store_id,
            "platform": platform,
        }

        if row is None:
            row = StorePlatformCredential(
                store_id=store_id,
                platform=platform,
                credential_type="oauth",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope,
                raw_payload_json=raw_payload_json,
                granted_identity_type="store",
                granted_identity_value=str(store_id),
                granted_identity_display=granted_identity_display,
            )
            session.add(row)
            await session.flush()
            return row

        row.credential_type = "oauth"
        row.access_token = access_token
        row.refresh_token = refresh_token
        row.expires_at = expires_at
        row.scope = scope
        row.raw_payload_json = raw_payload_json
        row.granted_identity_type = "store"
        row.granted_identity_value = str(store_id)
        row.granted_identity_display = granted_identity_display

        await session.flush()
        return row

    async def _upsert_connection(
        self,
        session: AsyncSession,
        *,
        store_id: int,
        platform: str,
        pull_ready: bool,
        now: datetime,
    ) -> StorePlatformConnection:
        row = (
            await session.execute(
                sa.select(StorePlatformConnection).where(
                    StorePlatformConnection.store_id == store_id,
                    StorePlatformConnection.platform == platform,
                )
            )
        ).scalar_one_or_none()

        if row is None:
            row = StorePlatformConnection(
                store_id=store_id,
                platform=platform,
            )
            session.add(row)

        row.auth_source = "oauth"
        row.connection_status = "connected"
        row.credential_status = "valid"
        row.reauth_required = False
        row.pull_ready = bool(pull_ready)
        row.status = "ready" if pull_ready else "authorized"
        row.status_reason = "mock_authorized"
        row.last_authorized_at = now
        row.last_pull_checked_at = now
        row.last_error_at = None

        await session.flush()
        return row

    async def _load_store(
        self,
        session: AsyncSession,
        *,
        store_id: int,
        platform: str,
    ) -> dict:
        row = (
            await session.execute(
                sa.text(
                    """
                    SELECT id, platform, store_code, store_name, active
                      FROM stores
                     WHERE id = :store_id
                     LIMIT 1
                    """
                ),
                {"store_id": int(store_id)},
            )
        ).mappings().first()

        if row is None:
            raise PlatformOrderIngestionMockServiceError(f"store not found: {store_id}")

        row_platform = self._validate_platform(str(row["platform"]))
        if row_platform != platform:
            raise PlatformOrderIngestionMockServiceError(
                f"store platform mismatch: store_id={store_id}, expected={platform}, actual={row_platform}"
            )

        if not bool(row["active"]):
            raise PlatformOrderIngestionMockServiceError(f"store is inactive: {store_id}")

        return dict(row)

    async def _mock_ingest_pdd_order(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        scenario: str,
        index: int,
        base_time: datetime,
    ) -> MockIngestRowResult:
        order_sn = self._build_platform_order_no(prefix="MOCKPDD", store_id=store_id, index=index)
        confirm_at = base_time - timedelta(minutes=index)
        items = self._build_pdd_items(scenario=scenario, index=index)
        detail = PddOrderDetail(
            order_sn=order_sn,
            province=None if scenario == "address_missing" else "上海市",
            city=None if scenario == "address_missing" else "上海市",
            town=None if scenario == "address_missing" else "浦东新区",
            receiver_name_masked=f"测试用户{index + 1}",
            receiver_phone_masked=f"1380000{index:04d}",
            receiver_address_masked=None
            if scenario == "address_missing"
            else f"张江高科技园区测试路{100 + index}号",
            buyer_memo=f"mock buyer memo #{index + 1}",
            remark=f"mock remark #{index + 1}",
            items=items,
            raw_payload={
                "source": "unified_mock",
                "mock": True,
                "platform": "pdd",
                "scenario": scenario,
                "order_sn": order_sn,
                "item_list": [item.raw_item for item in items],
            },
        )
        summary_raw_payload = {
            "source": "unified_mock",
            "mock": True,
            "platform": "pdd",
            "scenario": scenario,
            "order_sn": order_sn,
            "order_status": 1,
            "confirm_time": confirm_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "item_list": [item.raw_item for item in items],
        }

        order = await upsert_pdd_order(
            session,
            store_id=store_id,
            summary_raw_payload=summary_raw_payload,
            detail=detail,
            order_status=1,
            confirm_at=confirm_at,
        )
        await replace_pdd_order_items(
            session,
            pdd_order_id=int(order.id),
            order_sn=order_sn,
            detail=detail,
        )

        return MockIngestRowResult(
            platform_order_no=order_sn,
            native_order_id=int(order.id),
            scenario=scenario,
        )

    async def _mock_ingest_jd_order(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        scenario: str,
        index: int,
        base_time: datetime,
    ) -> MockIngestRowResult:
        order_id = self._build_platform_order_no(prefix="MOCKJD", store_id=store_id, index=index)
        start_time = (base_time - timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S")
        items = self._build_jd_items(scenario=scenario, index=index)
        total = self._sum_item_total([(item.item_price, item.item_total) for item in items])

        summary = JdOrderSummary(
            platform_order_id=order_id,
            order_state="WAIT_SELLER_STOCK_OUT",
            order_type="SOP",
            order_start_time=start_time,
            modified=start_time,
            consignee_name_masked=f"京东测试用户{index + 1}",
            consignee_mobile_masked=f"1390000{index:04d}",
            consignee_address_summary_masked=None
            if scenario == "address_missing"
            else f"北京市朝阳区测试路{100 + index}号",
            order_remark=f"mock jd remark #{index + 1}",
            order_total_price=str(total),
            items_count=len(items),
            raw_order={
                "source": "unified_mock",
                "mock": True,
                "platform": "jd",
                "scenario": scenario,
                "order_id": order_id,
            },
        )
        detail = JdOrderDetail(
            order_id=order_id,
            vender_id=f"VENDER-{store_id}",
            order_type="SOP",
            order_state="WAIT_SELLER_STOCK_OUT",
            buyer_pin=f"jd-buyer-{index + 1}",
            consignee_name=f"京东测试用户{index + 1}",
            consignee_mobile=f"1390000{index:04d}",
            consignee_phone=None,
            consignee_province=None if scenario == "address_missing" else "北京市",
            consignee_city=None if scenario == "address_missing" else "北京市",
            consignee_county=None if scenario == "address_missing" else "朝阳区",
            consignee_town=None if scenario == "address_missing" else "望京街道",
            consignee_address=None
            if scenario == "address_missing"
            else f"测试路{100 + index}号",
            order_remark=f"mock jd remark #{index + 1}",
            seller_remark=f"mock seller remark #{index + 1}",
            order_total_price=str(total),
            order_seller_price=str(total),
            freight_price="0.00",
            payment_confirm="true",
            order_start_time=start_time,
            order_end_time=None,
            modified=start_time,
            items=items,
            raw_payload={
                "source": "unified_mock",
                "mock": True,
                "platform": "jd",
                "scenario": scenario,
                "order_id": order_id,
                "itemInfoList": [item.raw_item for item in items],
            },
        )

        order = await upsert_jd_order(
            session,
            store_id=store_id,
            summary=summary,
            detail=detail,
        )
        await replace_jd_order_items(
            session,
            jd_order_id=int(order.id),
            order_id=order_id,
            detail=detail,
        )

        return MockIngestRowResult(
            platform_order_no=order_id,
            native_order_id=int(order.id),
            scenario=scenario,
        )

    async def _mock_ingest_taobao_order(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        scenario: str,
        index: int,
        base_time: datetime,
    ) -> MockIngestRowResult:
        tid = self._build_platform_order_no(prefix="MOCKTB", store_id=store_id, index=index)
        created = (base_time - timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S")
        items = self._build_taobao_items(tid=tid, scenario=scenario, index=index)
        total = self._sum_item_total([(item.price, item.num) for item in items])

        summary = TaobaoOrderSummary(
            tid=tid,
            status="WAIT_SELLER_SEND_GOODS",
            type="fixed",
            buyer_nick=f"tb-buyer-{index + 1}",
            buyer_open_uid=f"tb-open-{index + 1}",
            receiver_name=f"淘宝测试用户{index + 1}",
            receiver_mobile=f"1370000{index:04d}",
            receiver_state=None if scenario == "address_missing" else "浙江省",
            receiver_city=None if scenario == "address_missing" else "杭州市",
            receiver_district=None if scenario == "address_missing" else "西湖区",
            receiver_town=None if scenario == "address_missing" else "转塘街道",
            receiver_address=None
            if scenario == "address_missing"
            else f"云栖小镇测试路{100 + index}号",
            buyer_memo=f"mock taobao buyer memo #{index + 1}",
            seller_memo=f"mock taobao seller memo #{index + 1}",
            seller_flag=index % 6,
            payment=str(total),
            total_fee=str(total),
            post_fee="0.00",
            created=created,
            pay_time=created,
            modified=created,
            items_count=len(items),
            raw_order={
                "source": "unified_mock",
                "mock": True,
                "platform": "taobao",
                "scenario": scenario,
                "tid": tid,
            },
        )
        detail = TaobaoOrderDetail(
            tid=tid,
            status="WAIT_SELLER_SEND_GOODS",
            type="fixed",
            buyer_nick=summary.buyer_nick,
            buyer_open_uid=summary.buyer_open_uid,
            receiver_name=summary.receiver_name,
            receiver_mobile=summary.receiver_mobile,
            receiver_phone=None,
            receiver_state=summary.receiver_state,
            receiver_city=summary.receiver_city,
            receiver_district=summary.receiver_district,
            receiver_town=summary.receiver_town,
            receiver_address=summary.receiver_address,
            receiver_zip=None,
            buyer_memo=summary.buyer_memo,
            buyer_message=f"mock taobao buyer message #{index + 1}",
            seller_memo=summary.seller_memo,
            seller_flag=summary.seller_flag,
            payment=str(total),
            total_fee=str(total),
            post_fee="0.00",
            coupon_fee="0.00",
            created=created,
            pay_time=created,
            modified=created,
            items=items,
            raw_payload={
                "source": "unified_mock",
                "mock": True,
                "platform": "taobao",
                "scenario": scenario,
                "tid": tid,
                "orders": {"order": [item.raw_item for item in items]},
            },
        )

        order = await upsert_taobao_order(
            session,
            store_id=store_id,
            summary=summary,
            detail=detail,
        )
        await replace_taobao_order_items(
            session,
            taobao_order_id=int(order.id),
            tid=tid,
            detail=detail,
        )

        return MockIngestRowResult(
            platform_order_no=tid,
            native_order_id=int(order.id),
            scenario=scenario,
        )

    def _build_pdd_items(self, *, scenario: str, index: int) -> list[PddOrderDetailItem]:
        rows: list[PddOrderDetailItem] = []
        for offset in range(2):
            goods_price = 1299 + index * 10 + offset * 100
            outer_id: str | None = f"OUT-PDD-{index + 1}-{offset + 1}"
            if scenario == "item_abnormal" and offset == 0:
                goods_price = None
                outer_id = None

            raw_item = {
                "source": "unified_mock",
                "mock": True,
                "goods_id": f"PDD-G-{index + 1}-{offset + 1}",
                "sku_id": f"PDD-SKU-{index + 1}-{offset + 1}",
                "outer_id": outer_id,
                "goods_name": f"拼多多测试商品{index + 1}-{offset + 1}",
                "goods_count": offset + 1,
                "goods_price": goods_price,
            }
            rows.append(
                PddOrderDetailItem(
                    goods_id=raw_item["goods_id"],
                    goods_name=raw_item["goods_name"],
                    sku_id=raw_item["sku_id"],
                    outer_id=outer_id,
                    goods_count=offset + 1,
                    goods_price=goods_price,
                    raw_item=raw_item,
                )
            )
        return rows

    def _build_jd_items(self, *, scenario: str, index: int) -> list[JdOrderDetailItem]:
        rows: list[JdOrderDetailItem] = []
        for offset in range(2):
            item_price: str | None = str(Decimal("19.90") + Decimal(index) + Decimal(offset))
            outer_sku_id: str | None = f"OUT-JD-{index + 1}-{offset + 1}"
            if scenario == "item_abnormal" and offset == 0:
                item_price = None
                outer_sku_id = None

            raw_item = {
                "source": "unified_mock",
                "mock": True,
                "sku_id": f"JD-SKU-{index + 1}-{offset + 1}",
                "outer_sku_id": outer_sku_id,
                "ware_id": f"JD-WARE-{index + 1}-{offset + 1}",
                "item_name": f"京东测试商品{index + 1}-{offset + 1}",
                "item_total": offset + 1,
                "item_price": item_price,
            }
            rows.append(
                JdOrderDetailItem(
                    sku_id=raw_item["sku_id"],
                    outer_sku_id=outer_sku_id,
                    ware_id=raw_item["ware_id"],
                    item_name=raw_item["item_name"],
                    item_total=offset + 1,
                    item_price=item_price,
                    sku_name=f"规格{offset + 1}",
                    gift_point=0,
                    raw_item=raw_item,
                )
            )
        return rows

    def _build_taobao_items(
        self,
        *,
        tid: str,
        scenario: str,
        index: int,
    ) -> list[TaobaoOrderDetailItem]:
        rows: list[TaobaoOrderDetailItem] = []
        for offset in range(2):
            price: str | None = str(Decimal("29.90") + Decimal(index) + Decimal(offset))
            outer_sku_id: str | None = f"OUT-TB-SKU-{index + 1}-{offset + 1}"
            if scenario == "item_abnormal" and offset == 0:
                price = None
                outer_sku_id = None

            oid = f"{tid}-{offset + 1}"
            raw_item = {
                "source": "unified_mock",
                "mock": True,
                "oid": oid,
                "num_iid": f"TB-NUMIID-{index + 1}-{offset + 1}",
                "sku_id": f"TB-SKU-{index + 1}-{offset + 1}",
                "outer_iid": f"OUT-TB-ITEM-{index + 1}-{offset + 1}",
                "outer_sku_id": outer_sku_id,
                "title": f"淘宝测试商品{index + 1}-{offset + 1}",
                "price": price,
                "num": offset + 1,
                "payment": price,
                "total_fee": price,
                "sku_properties_name": f"颜色:测试{offset + 1}",
            }
            rows.append(
                TaobaoOrderDetailItem(
                    oid=oid,
                    num_iid=raw_item["num_iid"],
                    sku_id=raw_item["sku_id"],
                    outer_iid=raw_item["outer_iid"],
                    outer_sku_id=outer_sku_id,
                    title=raw_item["title"],
                    price=price,
                    num=offset + 1,
                    payment=price,
                    total_fee=price,
                    sku_properties_name=raw_item["sku_properties_name"],
                    raw_item=raw_item,
                )
            )
        return rows

    def _build_platform_order_no(self, *, prefix: str, store_id: int, index: int) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:8].upper()
        return f"{prefix}{store_id}{stamp}{index:03d}{suffix}"

    def _resolve_row_scenario(self, *, scenario: str, index: int) -> str:
        if scenario != "mixed":
            return scenario
        return ["normal", "address_missing", "item_abnormal"][index % 3]

    def _validate_store_id(self, store_id: int) -> int:
        store_id_int = int(store_id)
        if store_id_int <= 0:
            raise PlatformOrderIngestionMockServiceError("store_id must be positive")
        return store_id_int

    def _validate_count(self, count: int) -> None:
        if int(count) <= 0:
            raise PlatformOrderIngestionMockServiceError("count must be positive")
        if int(count) > 100:
            raise PlatformOrderIngestionMockServiceError("count must be <= 100")

    def _validate_platform(self, platform: str) -> str:
        value = str(platform or "").strip().lower()
        if value not in {"pdd", "jd", "taobao"}:
            raise PlatformOrderIngestionMockServiceError(f"unsupported platform: {value}")
        return value

    def _mock_scope(self, platform: str) -> str:
        if platform == "pdd":
            return "pdd.order.list.get,pdd.order.information.get"
        if platform == "jd":
            return "jingdong.pop.order.search,jingdong.pop.order.get"
        if platform == "taobao":
            return "taobao.trades.sold.get,taobao.trade.fullinfo.get"
        raise PlatformOrderIngestionMockServiceError(f"unsupported platform: {platform}")

    def _sum_item_total(self, items: list[tuple[str | None, int]]) -> Decimal:
        total = Decimal("0.00")
        for price, qty in items:
            if price is None:
                continue
            total += Decimal(str(price)) * Decimal(int(qty or 0))
        return total.quantize(Decimal("0.01"))
