# app/oms/services/order_ingest_service.py
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.order_event_bus import OrderEventBus
from app.oms.services.order_ingest_normalize import normalize_province_name
from app.oms.services.order_platform_adapters import get_adapter
from app.oms.services.order_utils import to_dec_str
from app.oms.services.platform_order_resolve_store import resolve_store_id

from app.oms.services.order_ingest_items_writer import insert_order_items
from app.oms.services.order_ingest_lines_writer import insert_order_lines
from app.oms.services.order_ingest_orders_writer import insert_order_or_get_idempotent


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _resolve_route_address(address: Optional[Mapping[str, str]]) -> tuple[str | None, str | None]:
    raw_province = _clean_text((address or {}).get("province"))
    raw_city = _clean_text((address or {}).get("city"))

    fallback_province = _clean_text(os.getenv("WMS_TEST_DEFAULT_PROVINCE"))
    fallback_city = _clean_text(os.getenv("WMS_TEST_DEFAULT_CITY"))

    province = normalize_province_name(raw_province or fallback_province)
    city = raw_city or fallback_city
    return province, city


async def _is_city_split_province(session: AsyncSession, *, province_code: str) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM warehouse_service_city_split_provinces
                 WHERE province_code = :prov
                 LIMIT 1
                """
            ),
            {"prov": str(province_code)},
        )
    ).first()
    return row is not None


async def _load_service_warehouse_by_province(
    session: AsyncSession,
    *,
    province_code: str,
) -> int | None:
    row = (
        await session.execute(
            text(
                """
                SELECT warehouse_id
                  FROM warehouse_service_provinces
                 WHERE province_code = :prov
                 LIMIT 1
                """
            ),
            {"prov": str(province_code)},
        )
    ).first()
    if not row or row[0] is None:
        return None
    wid = int(row[0])
    return wid if wid > 0 else None


async def _load_service_warehouse_by_city(
    session: AsyncSession,
    *,
    province_code: str,
    city_code: str,
) -> int | None:
    row = (
        await session.execute(
            text(
                """
                SELECT warehouse_id
                  FROM warehouse_service_cities
                 WHERE province_code = :prov
                   AND city_code = :city
                 LIMIT 1
                """
            ),
            {"prov": str(province_code), "city": str(city_code)},
        )
    ).first()
    if not row or row[0] is None:
        return None
    wid = int(row[0])
    return wid if wid > 0 else None


async def _resolve_route_payload(
    session: AsyncSession,
    *,
    address: Optional[Mapping[str, str]],
) -> dict[str, Any]:
    province, city = _resolve_route_address(address)

    if not province:
        return {
            "status": "FULFILLMENT_BLOCKED",
            "mode": "province",
            "reason": "PROVINCE_MISSING_OR_INVALID",
            "service_warehouse_id": None,
        }

    if await _is_city_split_province(session, province_code=province):
        if not city:
            return {
                "status": "FULFILLMENT_BLOCKED",
                "mode": "city",
                "reason": "NO_SERVICE_WAREHOUSE",
                "service_warehouse_id": None,
            }

        service_wh = await _load_service_warehouse_by_city(
            session,
            province_code=province,
            city_code=city,
        )
        if service_wh is None:
            return {
                "status": "FULFILLMENT_BLOCKED",
                "mode": "city",
                "reason": "NO_SERVICE_WAREHOUSE",
                "service_warehouse_id": None,
            }

        return {
            "status": "SERVICE_ASSIGNED",
            "mode": "city",
            "reason": "OK",
            "service_warehouse_id": int(service_wh),
        }

    service_wh = await _load_service_warehouse_by_province(session, province_code=province)
    if service_wh is None:
        return {
            "status": "FULFILLMENT_BLOCKED",
            "mode": "province",
            "reason": "NO_SERVICE_PROVINCE",
            "service_warehouse_id": None,
        }

    return {
        "status": "SERVICE_ASSIGNED",
        "mode": "province",
        "reason": "OK",
        "service_warehouse_id": int(service_wh),
    }


async def _upsert_order_fulfillment_route(
    session: AsyncSession,
    *,
    order_id: int,
    route_payload: Mapping[str, Any],
) -> None:
    route_status = str(route_payload.get("status") or "").strip().upper()
    planned_warehouse_id = route_payload.get("service_warehouse_id")
    planned_warehouse_id = int(planned_warehouse_id) if planned_warehouse_id is not None else None

    blocked_reasons_json: str | None = None
    if route_status == "FULFILLMENT_BLOCKED":
        reason = _clean_text(route_payload.get("reason"))
        blocked_reasons_json = json.dumps([reason] if reason else [], ensure_ascii=False)

    await session.execute(
        text(
            """
            INSERT INTO order_fulfillment (
              order_id,
              planned_warehouse_id,
              actual_warehouse_id,
              fulfillment_status,
              blocked_reasons
            )
            VALUES (
              :oid,
              :pwid,
              NULL,
              :fstat,
              CAST(:blocked_reasons_json AS jsonb)
            )
            ON CONFLICT (order_id) DO UPDATE
               SET planned_warehouse_id = EXCLUDED.planned_warehouse_id,
                   fulfillment_status  = EXCLUDED.fulfillment_status,
                   blocked_reasons     = EXCLUDED.blocked_reasons,
                   updated_at          = now()
            """
        ),
        {
            "oid": int(order_id),
            "pwid": planned_warehouse_id,
            "fstat": route_status,
            "blocked_reasons_json": blocked_reasons_json,
        },
    )


async def _load_existing_route_payload(
    session: AsyncSession,
    *,
    order_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  planned_warehouse_id,
                  fulfillment_status,
                  blocked_reasons
                FROM order_fulfillment
                WHERE order_id = :oid
                LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()

    if not row:
        return None

    planned_wh = row.get("planned_warehouse_id")
    planned_wh = int(planned_wh) if planned_wh is not None else None

    fstat = _clean_text(row.get("fulfillment_status"))
    blocked = row.get("blocked_reasons")

    reason: str | None = None
    if isinstance(blocked, list) and blocked:
        reason = _clean_text(blocked[0])
    elif blocked is not None:
        reason = _clean_text(blocked)

    if fstat == "SERVICE_ASSIGNED":
        return {
            "status": "SERVICE_ASSIGNED",
            "mode": None,
            "reason": "OK",
            "service_warehouse_id": planned_wh,
        }

    if fstat == "FULFILLMENT_BLOCKED":
        return {
            "status": "FULFILLMENT_BLOCKED",
            "mode": None,
            "reason": reason,
            "service_warehouse_id": planned_wh,
        }

    return {
        "status": fstat,
        "mode": None,
        "reason": reason,
        "service_warehouse_id": planned_wh,
    }


class OrderIngestService:
    """
    订单接入（ingest）主线 —— Route C（收敛版）

    ✅ 新主线合同（两态）：
      - OK / IDEMPOTENT：订单落库 + 行事实 + 地址快照 + 触发 routing 写入 order_fulfillment（planned/actual）
      - FULFILLMENT_BLOCKED：省份缺失 / 服务仓未配置（显式暴露，等待人工/配置修复）

    ❌ 明确不做：
      - ingest 阶段库存判断
      - ingest 阶段自动 reserve（库存不足由人工改派/退单处理）
      - ingest 阶段探测 orders 是否存在 warehouse_id（routing 自己写 order_fulfillment）
    """

    @staticmethod
    async def ingest_raw(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict:
        adapter = get_adapter(platform)
        co = adapter.normalize({**payload, "store_code": store_code})
        return await OrderIngestService.ingest(
            session,
            platform=co["platform"],
            store_code=co["store_code"],
            ext_order_no=co["ext_order_no"],
            occurred_at=co["occurred_at"],
            buyer_name=co.get("buyer_name"),
            buyer_phone=co.get("buyer_phone"),
            order_amount=co.get("order_amount", 0),
            pay_amount=co.get("pay_amount", 0),
            items=co.get("lines", ()),
            address=co.get("address"),
            extras=co.get("extras"),
            trace_id=trace_id,
        )

    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        ext_order_no: str,
        occurred_at: Optional[datetime] = None,
        buyer_name: Optional[str] = None,
        buyer_phone: Optional[str] = None,
        order_amount: Decimal | int | float | str = 0,
        pay_amount: Decimal | int | float | str = 0,
        items: Sequence[Mapping[str, Any]] = (),
        address: Optional[Mapping[str, str]] = None,
        extras: Optional[Mapping[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        plat = (platform or "").upper().strip()
        occurred_at = occurred_at or datetime.now(timezone.utc)
        order_ref = f"ORD:{plat}:{store_code}:{ext_order_no}"

        orders_has_extras = False
        order_items_has_extras = False

        store_id = await resolve_store_id(
            session,
            platform=plat,
            store_code=store_code,
            store_name=str(store_code),
        )

        # 1) orders（幂等）
        ins_res = await insert_order_or_get_idempotent(
            session,
            platform=plat,
            store_code=store_code,
            store_id=store_id,
            ext_order_no=ext_order_no,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=order_amount,
            pay_amount=pay_amount,
            items=items,
            extras=extras,
            trace_id=trace_id,
            orders_has_extras=orders_has_extras,
            order_ref=order_ref,
        )

        idempotent_hit = ins_res.get("status") == "IDEMPOTENT"

        order_id_raw = ins_res.get("id")
        if order_id_raw is None:
            raise RuntimeError("订单接入失败：insert_order_or_get_idempotent 未返回 id")
        order_id = int(order_id_raw)

        # 2) order_items（非幂等才写）
        if not idempotent_hit:
            await insert_order_items(
                session,
                order_id=order_id,
                items=items,
                order_items_has_extras=order_items_has_extras,
            )

            # 3) ORDER_CREATED（非幂等才写）
            try:
                await OrderEventBus.order_created(
                    session,
                    ref=order_ref,
                    platform=plat,
                    store_code=store_code,
                    order_id=order_id,
                    order_amount=to_dec_str(order_amount),
                    pay_amount=to_dec_str(pay_amount),
                    lines=len(items or ()),
                    trace_id=trace_id,
                )
            except Exception:
                pass

        # 3.25) order_lines（标准化行事实：解释/作业共用）
        try:
            if items:
                await insert_order_lines(session, order_id=order_id, items=items)
        except Exception:
            pass

        # 4) ingest 阶段路由：写 order_fulfillment（planned/status/blocked_reasons）
        if not idempotent_hit:
            route_payload = await _resolve_route_payload(session, address=address)
            await _upsert_order_fulfillment_route(
                session,
                order_id=order_id,
                route_payload=route_payload,
            )
        else:
            route_payload = await _load_existing_route_payload(session, order_id=order_id)
            if route_payload is None:
                route_payload = await _resolve_route_payload(session, address=address)

        route_status = str(route_payload.get("status") or "UNKNOWN")

        return {
            "status": (
                "IDEMPOTENT"
                if idempotent_hit
                else ("FULFILLMENT_BLOCKED" if route_status == "FULFILLMENT_BLOCKED" else "OK")
            ),
            "id": order_id,
            "ref": order_ref,
            "route": route_payload,
            "ingest_state": "CREATED",
            "route_status": route_status,
        }
