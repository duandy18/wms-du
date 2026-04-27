from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import List, Optional, Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.oms.platforms.models.pdd_order import PddOrder, PddOrderItem
from app.oms.platforms.models.pdd_order_order_mapping import PddOrderOrderMapping
from app.oms.platforms.pdd.contracts import PddOrderDetail


_MONEY_SCALE = Decimal("100")


def _money_from_cent(raw: object) -> Decimal | None:
    """
    平台金额（分） -> 元 Decimal(14,2) 语义。
    """
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return (value / _MONEY_SCALE).quantize(Decimal("0.01"))


async def load_store_code_by_store_id_for_pdd(
    session: AsyncSession,
    *,
    store_id: int,
) -> str:
    """
    PDD 拉单入库使用的店铺编码读取入口。

    边界：
    - 只读取 stores.store_code；
    - 只接受 platform=PDD 的店铺；
    - 不创建店铺；
    - 不修正平台；
    - 找不到即抛 LookupError，由调用方转为 400。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT store_code
                  FROM stores
                 WHERE id = :store_id
                   AND upper(platform) = 'PDD'
                 LIMIT 1
                """
            ),
            {"store_id": int(store_id)},
        )
    ).mappings().first()

    store_code = row.get("store_code") if row else None
    if not store_code:
        raise LookupError(f"pdd store not found: store_id={int(store_id)}")

    return str(store_code)


async def get_pdd_order_by_store_and_order_sn(
    session: AsyncSession,
    *,
    store_id: int,
    order_sn: str,
) -> Optional[PddOrder]:
    stmt = (
        select(PddOrder)
        .where(
            PddOrder.store_id == int(store_id),
            PddOrder.order_sn == str(order_sn).strip(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pdd_order_with_items(
    session: AsyncSession,
    *,
    pdd_order_id: int,
) -> Optional[PddOrder]:
    stmt = (
        select(PddOrder)
        .options(
            selectinload(PddOrder.items),
            selectinload(PddOrder.order_mapping),
        )
        .where(PddOrder.id == int(pdd_order_id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_pdd_orders(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
) -> Sequence[PddOrder]:
    stmt = (
        select(PddOrder)
        .order_by(PddOrder.id.desc())
        .limit(int(limit))
        .offset(int(offset))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert_pdd_order(
    session: AsyncSession,
    *,
    store_id: int,
    summary_raw_payload: dict | None,
    detail: PddOrderDetail,
    order_status: int | str | None,
    confirm_at,
) -> PddOrder:
    """
    以 (store_id, order_sn) 为唯一锚点 upsert pdd_orders。
    """
    order_sn = str(detail.order_sn or "").strip()
    if not order_sn:
        raise ValueError("detail.order_sn is required")

    existing = await get_pdd_order_by_store_and_order_sn(
        session,
        store_id=int(store_id),
        order_sn=order_sn,
    )

    goods_amount: Decimal | None = None
    pay_amount: Decimal | None = None

    if detail.items:
        line_amounts: List[Decimal] = []
        for item in detail.items:
            unit_price = _money_from_cent(item.goods_price)
            if unit_price is None:
                continue
            qty = int(item.goods_count or 0)
            line_amounts.append((unit_price * Decimal(qty)).quantize(Decimal("0.01")))
        if line_amounts:
            goods_amount = sum(line_amounts, Decimal("0.00")).quantize(Decimal("0.01"))
            pay_amount = goods_amount

    if existing is None:
        obj = PddOrder(
            store_id=int(store_id),
            order_sn=order_sn,
            order_status=str(order_status) if order_status is not None else None,
            receiver_name=detail.receiver_name_masked,
            receiver_phone=detail.receiver_phone_masked,
            receiver_province=detail.province,
            receiver_city=detail.city,
            receiver_district=detail.town,
            receiver_address=detail.receiver_address_masked,
            buyer_memo=detail.buyer_memo,
            remark=detail.remark,
            confirm_at=confirm_at,
            goods_amount=goods_amount,
            pay_amount=pay_amount,
            raw_summary_payload=summary_raw_payload,
            raw_detail_payload=detail.raw_payload,
        )
        session.add(obj)
        await session.flush()
        return obj

    existing.order_status = str(order_status) if order_status is not None else None
    existing.receiver_name = detail.receiver_name_masked
    existing.receiver_phone = detail.receiver_phone_masked
    existing.receiver_province = detail.province
    existing.receiver_city = detail.city
    existing.receiver_district = detail.town
    existing.receiver_address = detail.receiver_address_masked
    existing.buyer_memo = detail.buyer_memo
    existing.remark = detail.remark
    existing.confirm_at = confirm_at
    existing.goods_amount = goods_amount
    existing.pay_amount = pay_amount
    existing.raw_summary_payload = summary_raw_payload
    existing.raw_detail_payload = detail.raw_payload
    return existing


async def replace_pdd_order_items(
    session: AsyncSession,
    *,
    pdd_order_id: int,
    order_sn: str,
    detail: PddOrderDetail,
) -> Sequence[PddOrderItem]:
    """
    第一版采用“先删后建”，保证和最新详情对齐。
    仅保存平台原生商品行字段。
    """
    await session.execute(
        delete(PddOrderItem).where(PddOrderItem.pdd_order_id == int(pdd_order_id))
    )

    created: List[PddOrderItem] = []
    for item in detail.items:
        unit_price = _money_from_cent(item.goods_price)
        qty = int(item.goods_count or 0)

        obj = PddOrderItem(
            pdd_order_id=int(pdd_order_id),
            order_sn=str(order_sn).strip(),
            platform_goods_id=item.goods_id,
            platform_sku_id=item.sku_id,
            outer_id=item.outer_id,
            goods_name=item.goods_name,
            goods_count=qty,
            goods_price=unit_price,
            raw_item_payload=item.raw_item,
        )
        session.add(obj)
        created.append(obj)

    await session.flush()
    return created


async def get_pdd_order_mapping_by_pdd_order_id(
    session: AsyncSession,
    *,
    pdd_order_id: int,
) -> Optional[PddOrderOrderMapping]:
    stmt = (
        select(PddOrderOrderMapping)
        .where(PddOrderOrderMapping.pdd_order_id == int(pdd_order_id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_pdd_order_mapping(
    session: AsyncSession,
    *,
    pdd_order_id: int,
    order_id: int,
    mapping_source: str = "system",
    remark: str | None = None,
    created_by: int | None = None,
) -> PddOrderOrderMapping:
    obj = PddOrderOrderMapping(
        pdd_order_id=int(pdd_order_id),
        order_id=int(order_id),
        mapping_source=str(mapping_source or "system"),
        remark=remark,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(obj)
    await session.flush()
    return obj
