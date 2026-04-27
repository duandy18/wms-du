# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform_order_ingestion.models.taobao_order import TaobaoOrder, TaobaoOrderItem
from app.platform_order_ingestion.taobao.service_order_detail import TaobaoOrderDetail
from app.platform_order_ingestion.taobao.service_real_pull import TaobaoOrderSummary


async def list_taobao_orders(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[TaobaoOrder]:
    stmt = (
        sa.select(TaobaoOrder)
        .order_by(
            TaobaoOrder.last_synced_at.desc(),
            TaobaoOrder.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_taobao_order_with_items(
    session: AsyncSession,
    *,
    taobao_order_id: int,
) -> TaobaoOrder | None:
    stmt = (
        sa.select(TaobaoOrder)
        .options(selectinload(TaobaoOrder.items))
        .where(TaobaoOrder.id == taobao_order_id)
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


async def load_store_code_by_store_id_for_taobao(
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
                   AND lower(platform) = 'taobao'
                 LIMIT 1
                """
            ),
            {"store_id": int(store_id)},
        )
    ).mappings().first()

    store_code = row.get("store_code") if row else None
    if not store_code:
        raise LookupError(f"taobao store not found: store_id={int(store_id)}")

    return str(store_code)


async def get_taobao_order_by_store_and_tid(
    session: AsyncSession,
    *,
    store_id: int,
    tid: str,
) -> TaobaoOrder | None:
    stmt = (
        sa.select(TaobaoOrder)
        .where(
            TaobaoOrder.store_id == int(store_id),
            TaobaoOrder.tid == str(tid).strip(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_taobao_order(
    session: AsyncSession,
    *,
    store_id: int,
    summary: TaobaoOrderSummary,
    detail: TaobaoOrderDetail,
) -> TaobaoOrder:
    tid = str(detail.tid or summary.tid or "").strip()
    if not tid:
        raise ValueError("detail.tid is required")

    existing = await get_taobao_order_by_store_and_tid(
        session,
        store_id=int(store_id),
        tid=tid,
    )

    values = {
        "store_id": int(store_id),
        "tid": tid,
        "status": detail.status or summary.status,
        "type": detail.type or summary.type,
        "buyer_nick": detail.buyer_nick or summary.buyer_nick,
        "buyer_open_uid": detail.buyer_open_uid or summary.buyer_open_uid,
        "receiver_name": detail.receiver_name or summary.receiver_name,
        "receiver_mobile": detail.receiver_mobile or summary.receiver_mobile,
        "receiver_phone": detail.receiver_phone or summary.receiver_phone,
        "receiver_state": detail.receiver_state or summary.receiver_state,
        "receiver_city": detail.receiver_city or summary.receiver_city,
        "receiver_district": detail.receiver_district or summary.receiver_district,
        "receiver_town": detail.receiver_town or summary.receiver_town,
        "receiver_address": detail.receiver_address or summary.receiver_address,
        "receiver_zip": detail.receiver_zip or summary.receiver_zip,
        "buyer_memo": detail.buyer_memo or summary.buyer_memo,
        "buyer_message": detail.buyer_message or summary.buyer_message,
        "seller_memo": detail.seller_memo or summary.seller_memo,
        "seller_flag": detail.seller_flag if detail.seller_flag is not None else summary.seller_flag,
        "payment": _money(detail.payment or summary.payment),
        "total_fee": _money(detail.total_fee or summary.total_fee),
        "post_fee": _money(detail.post_fee or summary.post_fee),
        "coupon_fee": _money(detail.coupon_fee),
        "created": _parse_optional_dt(detail.created or summary.created),
        "pay_time": _parse_optional_dt(detail.pay_time or summary.pay_time),
        "modified": _parse_optional_dt(detail.modified or summary.modified),
        "raw_summary_payload": summary.raw_order,
        "raw_detail_payload": detail.raw_payload,
    }

    if existing is None:
        obj = TaobaoOrder(**values)
        session.add(obj)
        await session.flush()
        return obj

    for key, value in values.items():
        setattr(existing, key, value)

    await session.flush()
    return existing


async def replace_taobao_order_items(
    session: AsyncSession,
    *,
    taobao_order_id: int,
    tid: str,
    detail: TaobaoOrderDetail,
) -> list[TaobaoOrderItem]:
    await session.execute(
        sa.delete(TaobaoOrderItem).where(TaobaoOrderItem.taobao_order_id == int(taobao_order_id))
    )

    created: list[TaobaoOrderItem] = []
    for item in detail.items or []:
        oid = str(item.oid or "").strip()
        if not oid:
            continue

        obj = TaobaoOrderItem(
            taobao_order_id=int(taobao_order_id),
            tid=str(tid).strip(),
            oid=oid,
            num_iid=item.num_iid,
            sku_id=item.sku_id,
            outer_iid=item.outer_iid,
            outer_sku_id=item.outer_sku_id,
            title=item.title,
            price=_money(item.price),
            num=int(item.num or 0),
            payment=_money(item.payment),
            total_fee=_money(item.total_fee),
            sku_properties_name=item.sku_properties_name,
            raw_item_payload=item.raw_item,
        )
        session.add(obj)
        created.append(obj)

    await session.flush()
    return created
