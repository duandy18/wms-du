from __future__ import annotations

from decimal import Decimal
from typing import List

from app.models.taobao_order import TaobaoOrder, TaobaoOrderItem
from app.oms.platforms.taobao.contracts_ledger import (
    TaobaoOrderLedgerDetailOut,
    TaobaoOrderLedgerItemOut,
    TaobaoOrderLedgerRowOut,
)
from app.oms.platforms.taobao.repo_orders import (
    get_taobao_order_with_items,
    list_taobao_orders,
)


def _fmt_dt(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _fmt_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_row(row: TaobaoOrder) -> TaobaoOrderLedgerRowOut:
    return TaobaoOrderLedgerRowOut(
        id=int(row.id),
        store_id=int(row.store_id),
        tid=str(row.tid),
        status=row.status,
        type=row.type,
        created=_fmt_dt(row.created),
        pay_time=_fmt_dt(row.pay_time),
        payment=_fmt_decimal(row.payment),
        total_fee=_fmt_decimal(row.total_fee),
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
    )


def _serialize_item(item: TaobaoOrderItem) -> TaobaoOrderLedgerItemOut:
    return TaobaoOrderLedgerItemOut(
        id=int(item.id),
        taobao_order_id=int(item.taobao_order_id),
        tid=str(item.tid),
        oid=str(item.oid),
        num_iid=item.num_iid,
        sku_id=item.sku_id,
        outer_iid=item.outer_iid,
        outer_sku_id=item.outer_sku_id,
        title=item.title,
        price=_fmt_decimal(item.price),
        num=int(item.num),
        payment=_fmt_decimal(item.payment),
        total_fee=_fmt_decimal(item.total_fee),
        sku_properties_name=item.sku_properties_name,
        raw_item_payload=item.raw_item_payload,
    )


def _serialize_detail(row: TaobaoOrder) -> TaobaoOrderLedgerDetailOut:
    items: List[TaobaoOrderLedgerItemOut] = [_serialize_item(x) for x in (row.items or [])]
    return TaobaoOrderLedgerDetailOut(
        id=int(row.id),
        store_id=int(row.store_id),
        tid=str(row.tid),
        status=row.status,
        type=row.type,
        buyer_nick=row.buyer_nick,
        buyer_open_uid=row.buyer_open_uid,
        receiver_name=row.receiver_name,
        receiver_mobile=row.receiver_mobile,
        receiver_phone=row.receiver_phone,
        receiver_state=row.receiver_state,
        receiver_city=row.receiver_city,
        receiver_district=row.receiver_district,
        receiver_town=row.receiver_town,
        receiver_address=row.receiver_address,
        receiver_zip=row.receiver_zip,
        buyer_memo=row.buyer_memo,
        buyer_message=row.buyer_message,
        seller_memo=row.seller_memo,
        seller_flag=row.seller_flag,
        payment=_fmt_decimal(row.payment),
        total_fee=_fmt_decimal(row.total_fee),
        post_fee=_fmt_decimal(row.post_fee),
        coupon_fee=_fmt_decimal(row.coupon_fee),
        created=_fmt_dt(row.created),
        pay_time=_fmt_dt(row.pay_time),
        modified=_fmt_dt(row.modified),
        raw_summary_payload=row.raw_summary_payload,
        raw_detail_payload=row.raw_detail_payload,
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
        created_at=_fmt_dt(row.created_at),
        updated_at=_fmt_dt(row.updated_at),
        items=items,
    )


async def list_taobao_order_ledger_rows(
    session,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[TaobaoOrderLedgerRowOut]:
    rows = await list_taobao_orders(
        session,
        limit=limit,
        offset=offset,
    )
    return [_serialize_row(x) for x in rows]


async def get_taobao_order_ledger_detail(
    session,
    *,
    taobao_order_id: int,
) -> TaobaoOrderLedgerDetailOut | None:
    row = await get_taobao_order_with_items(
        session,
        taobao_order_id=taobao_order_id,
    )
    if row is None:
        return None
    return _serialize_detail(row)
