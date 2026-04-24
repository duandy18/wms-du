from __future__ import annotations

from decimal import Decimal
from typing import List

from app.oms.platforms.models.jd_order import JdOrder, JdOrderItem
from app.oms.platforms.jd.contracts_ledger import (
    JdOrderLedgerDetailOut,
    JdOrderLedgerItemOut,
    JdOrderLedgerRowOut,
)
from app.oms.platforms.jd.repo_orders import (
    get_jd_order_with_items,
    list_jd_orders,
)


def _fmt_dt(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _fmt_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_row(row: JdOrder) -> JdOrderLedgerRowOut:
    return JdOrderLedgerRowOut(
        id=int(row.id),
        store_id=int(row.store_id),
        order_id=str(row.order_id),
        order_state=row.order_state,
        order_type=row.order_type,
        order_start_time=_fmt_dt(row.order_start_time),
        modified=_fmt_dt(row.modified),
        order_total_price=_fmt_decimal(row.order_total_price),
        order_seller_price=_fmt_decimal(row.order_seller_price),
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
    )


def _serialize_item(item: JdOrderItem) -> JdOrderLedgerItemOut:
    return JdOrderLedgerItemOut(
        id=int(item.id),
        jd_order_id=int(item.jd_order_id),
        order_id=str(item.order_id),
        sku_id=item.sku_id,
        outer_sku_id=item.outer_sku_id,
        ware_id=item.ware_id,
        item_name=item.item_name,
        item_total=int(item.item_total),
        item_price=_fmt_decimal(item.item_price),
        sku_name=item.sku_name,
        gift_point=item.gift_point,
        raw_item_payload=item.raw_item_payload,
    )


def _serialize_detail(row: JdOrder) -> JdOrderLedgerDetailOut:
    items: List[JdOrderLedgerItemOut] = [_serialize_item(x) for x in (row.items or [])]
    return JdOrderLedgerDetailOut(
        id=int(row.id),
        store_id=int(row.store_id),
        order_id=str(row.order_id),
        vender_id=row.vender_id,
        order_type=row.order_type,
        order_state=row.order_state,
        buyer_pin=row.buyer_pin,
        consignee_name=row.consignee_name,
        consignee_mobile=row.consignee_mobile,
        consignee_phone=row.consignee_phone,
        consignee_province=row.consignee_province,
        consignee_city=row.consignee_city,
        consignee_county=row.consignee_county,
        consignee_town=row.consignee_town,
        consignee_address=row.consignee_address,
        order_remark=row.order_remark,
        seller_remark=row.seller_remark,
        order_total_price=_fmt_decimal(row.order_total_price),
        order_seller_price=_fmt_decimal(row.order_seller_price),
        freight_price=_fmt_decimal(row.freight_price),
        payment_confirm=row.payment_confirm,
        order_start_time=_fmt_dt(row.order_start_time),
        order_end_time=_fmt_dt(row.order_end_time),
        modified=_fmt_dt(row.modified),
        raw_summary_payload=row.raw_summary_payload,
        raw_detail_payload=row.raw_detail_payload,
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
        created_at=_fmt_dt(row.created_at),
        updated_at=_fmt_dt(row.updated_at),
        items=items,
    )


async def list_jd_order_ledger_rows(
    session,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[JdOrderLedgerRowOut]:
    rows = await list_jd_orders(
        session,
        limit=limit,
        offset=offset,
    )
    return [_serialize_row(x) for x in rows]


async def get_jd_order_ledger_detail(
    session,
    *,
    jd_order_id: int,
) -> JdOrderLedgerDetailOut | None:
    row = await get_jd_order_with_items(
        session,
        jd_order_id=jd_order_id,
    )
    if row is None:
        return None
    return _serialize_detail(row)
