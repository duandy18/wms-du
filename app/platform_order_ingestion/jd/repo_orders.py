# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform_order_ingestion.models.jd_order import JdOrder, JdOrderItem
from app.platform_order_ingestion.jd.service_order_detail import JdOrderDetail
from app.platform_order_ingestion.jd.service_real_pull import JdOrderSummary


async def list_jd_orders(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[JdOrder]:
    stmt = (
        sa.select(JdOrder)
        .order_by(JdOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_jd_order_with_items(
    session: AsyncSession,
    *,
    jd_order_id: int,
) -> JdOrder | None:
    stmt = (
        sa.select(JdOrder)
        .where(JdOrder.id == jd_order_id)
        .options(selectinload(JdOrder.items))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

_MONEY_QUANT = Decimal("0.01")


def _money(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(_MONEY_QUANT)
    except (InvalidOperation, ValueError):
        return None


def _parse_optional_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def load_store_code_by_store_id_for_jd(
    session: AsyncSession,
    *,
    store_id: int,
) -> str:
    row = (
        await session.execute(
            sa.text(
                """
                SELECT store_code
                  FROM stores
                 WHERE id = :store_id
                   AND lower(platform) = 'jd'
                 LIMIT 1
                """
            ),
            {"store_id": int(store_id)},
        )
    ).mappings().first()

    store_code = row.get("store_code") if row else None
    if not store_code:
        raise LookupError(f"jd store not found: store_id={int(store_id)}")

    return str(store_code)


async def get_jd_order_by_store_and_order_id(
    session: AsyncSession,
    *,
    store_id: int,
    order_id: str,
) -> JdOrder | None:
    stmt = (
        sa.select(JdOrder)
        .where(
            JdOrder.store_id == int(store_id),
            JdOrder.order_id == str(order_id).strip(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_jd_order(
    session: AsyncSession,
    *,
    store_id: int,
    summary: JdOrderSummary,
    detail: JdOrderDetail,
) -> JdOrder:
    order_id = str(detail.order_id or summary.platform_order_id or "").strip()
    if not order_id:
        raise ValueError("detail.order_id is required")

    existing = await get_jd_order_by_store_and_order_id(
        session,
        store_id=int(store_id),
        order_id=order_id,
    )

    values = {
        "store_id": int(store_id),
        "order_id": order_id,
        "vender_id": detail.vender_id,
        "order_type": detail.order_type or summary.order_type,
        "order_state": detail.order_state or summary.order_state,
        "buyer_pin": detail.buyer_pin,
        "consignee_name": detail.consignee_name or summary.consignee_name_masked,
        "consignee_mobile": detail.consignee_mobile or summary.consignee_mobile_masked,
        "consignee_phone": detail.consignee_phone,
        "consignee_province": detail.consignee_province,
        "consignee_city": detail.consignee_city,
        "consignee_county": detail.consignee_county,
        "consignee_town": detail.consignee_town,
        "consignee_address": detail.consignee_address or summary.consignee_address_summary_masked,
        "order_remark": detail.order_remark or summary.order_remark,
        "seller_remark": detail.seller_remark,
        "order_total_price": _money(detail.order_total_price or summary.order_total_price),
        "order_seller_price": _money(detail.order_seller_price),
        "freight_price": _money(detail.freight_price),
        "payment_confirm": detail.payment_confirm,
        "order_start_time": _parse_optional_dt(detail.order_start_time or summary.order_start_time),
        "order_end_time": _parse_optional_dt(detail.order_end_time),
        "modified": _parse_optional_dt(detail.modified or summary.modified),
        "raw_summary_payload": summary.raw_order,
        "raw_detail_payload": detail.raw_payload,
    }

    if existing is None:
        obj = JdOrder(**values)
        session.add(obj)
        await session.flush()
        return obj

    for key, value in values.items():
        setattr(existing, key, value)

    await session.flush()
    return existing


async def replace_jd_order_items(
    session: AsyncSession,
    *,
    jd_order_id: int,
    order_id: str,
    detail: JdOrderDetail,
) -> list[JdOrderItem]:
    await session.execute(
        sa.delete(JdOrderItem).where(JdOrderItem.jd_order_id == int(jd_order_id))
    )

    created: list[JdOrderItem] = []
    for item in detail.items or []:
        obj = JdOrderItem(
            jd_order_id=int(jd_order_id),
            order_id=str(order_id).strip(),
            sku_id=item.sku_id,
            outer_sku_id=item.outer_sku_id,
            ware_id=item.ware_id,
            item_name=item.item_name,
            item_total=int(item.item_total or 0),
            item_price=_money(item.item_price),
            sku_name=item.sku_name,
            gift_point=item.gift_point,
            raw_item_payload=item.raw_item,
        )
        session.add(obj)
        created.append(obj)

    await session.flush()
    return created
