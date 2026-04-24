from __future__ import annotations

from decimal import Decimal
from typing import List

from app.oms.platforms.models.pdd_order import PddOrder, PddOrderItem
from app.oms.platforms.pdd.contracts_ledger import (
    PddOrderLedgerDetailOut,
    PddOrderLedgerItemOut,
    PddOrderLedgerRowOut,
)
from app.oms.platforms.pdd.repo_orders import (
    get_pdd_order_with_items,
    list_pdd_orders,
)


def _fmt_dt(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _fmt_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _serialize_row(row: PddOrder) -> PddOrderLedgerRowOut:
    return PddOrderLedgerRowOut(
        id=int(row.id),
        store_id=int(row.store_id),
        order_sn=str(row.order_sn),
        order_status=row.order_status,
        confirm_at=_fmt_dt(row.confirm_at),
        goods_amount=_fmt_decimal(row.goods_amount),
        pay_amount=_fmt_decimal(row.pay_amount),
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
    )


def _serialize_item(item: PddOrderItem) -> PddOrderLedgerItemOut:
    return PddOrderLedgerItemOut(
        id=int(item.id),
        pdd_order_id=int(item.pdd_order_id),
        order_sn=str(item.order_sn),
        platform_goods_id=item.platform_goods_id,
        platform_sku_id=item.platform_sku_id,
        outer_id=item.outer_id,
        goods_name=item.goods_name,
        goods_count=int(item.goods_count),
        goods_price=_fmt_decimal(item.goods_price),
        raw_item_payload=item.raw_item_payload,
    )


def _serialize_detail(row: PddOrder) -> PddOrderLedgerDetailOut:
    items: List[PddOrderLedgerItemOut] = [_serialize_item(x) for x in (row.items or [])]
    return PddOrderLedgerDetailOut(
        id=int(row.id),
        store_id=int(row.store_id),
        order_sn=str(row.order_sn),
        order_status=row.order_status,
        receiver_name=row.receiver_name,
        receiver_phone=row.receiver_phone,
        receiver_province=row.receiver_province,
        receiver_city=row.receiver_city,
        receiver_district=row.receiver_district,
        receiver_address=row.receiver_address,
        buyer_memo=row.buyer_memo,
        remark=row.remark,
        confirm_at=_fmt_dt(row.confirm_at),
        goods_amount=_fmt_decimal(row.goods_amount),
        pay_amount=_fmt_decimal(row.pay_amount),
        raw_summary_payload=row.raw_summary_payload,
        raw_detail_payload=row.raw_detail_payload,
        pulled_at=_fmt_dt(row.pulled_at),
        last_synced_at=_fmt_dt(row.last_synced_at),
        created_at=_fmt_dt(row.created_at),
        updated_at=_fmt_dt(row.updated_at),
        items=items,
    )


async def list_pdd_order_ledger_rows(
    session,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[PddOrderLedgerRowOut]:
    rows = await list_pdd_orders(
        session,
        limit=limit,
        offset=offset,
    )
    return [_serialize_row(x) for x in rows]


async def get_pdd_order_ledger_detail(
    session,
    *,
    pdd_order_id: int,
) -> PddOrderLedgerDetailOut | None:
    row = await get_pdd_order_with_items(session, pdd_order_id=pdd_order_id)
    if row is None:
        return None
    return _serialize_detail(row)
