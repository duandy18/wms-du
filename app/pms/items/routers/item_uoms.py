# app/pms/items/routers/item_uoms.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.inbound_receipt import InboundReceiptLine
from app.models.item_barcode import ItemBarcode
from app.models.item_uom import ItemUOM
from app.models.purchase_order_line import PurchaseOrderLine
from app.pms.items.contracts.item_uom import (
    ItemUomCreate,
    ItemUomOut,
    ItemUomUpdate,
)

router = APIRouter(prefix="/item-uoms", tags=["item-uoms"])


async def _get_item_uom_or_404(session: AsyncSession, item_uom_id: int) -> ItemUOM:
    obj = await session.get(ItemUOM, int(item_uom_id))
    if not obj:
        raise HTTPException(status_code=404, detail="ItemUom not found")
    return obj


async def _has_barcode_refs(
    session: AsyncSession,
    *,
    item_id: int,
    item_uom_id: int,
) -> bool:
    stmt = (
        select(ItemBarcode.id)
        .where(
            ItemBarcode.item_id == int(item_id),
            ItemBarcode.item_uom_id == int(item_uom_id),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _has_po_line_refs(session: AsyncSession, *, item_uom_id: int) -> bool:
    stmt = (
        select(PurchaseOrderLine.id)
        .where(PurchaseOrderLine.purchase_uom_id_snapshot == int(item_uom_id))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _has_receipt_line_refs(session: AsyncSession, *, item_uom_id: int) -> bool:
    stmt = (
        select(InboundReceiptLine.id)
        .where(InboundReceiptLine.uom_id == int(item_uom_id))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _find_base_uom(
    session: AsyncSession,
    *,
    item_id: int,
    exclude_id: int,
) -> ItemUOM | None:
    stmt = (
        select(ItemUOM)
        .where(
            ItemUOM.item_id == int(item_id),
            ItemUOM.is_base.is_(True),
            ItemUOM.id != int(exclude_id),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


@router.post("", response_model=ItemUomOut)
async def create_item_uom(
    payload: ItemUomCreate,
    session: AsyncSession = Depends(get_session),
):
    obj = ItemUOM(**payload.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("/item/{item_id}", response_model=list[ItemUomOut])
async def list_item_uoms(
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    q = await session.execute(select(ItemUOM).where(ItemUOM.item_id == item_id))
    return q.scalars().all()


@router.get("/by-items", response_model=list[ItemUomOut])
async def list_item_uoms_for_items(
    item_id: list[int] = Query(default=[]),
    session: AsyncSession = Depends(get_session),
):
    ids = [int(x) for x in item_id if int(x) > 0]
    if not ids:
        return []

    q = await session.execute(select(ItemUOM).where(ItemUOM.item_id.in_(ids)))
    return q.scalars().all()


@router.patch("/{id}", response_model=ItemUomOut)
async def update_item_uom(
    id: int,
    payload: ItemUomUpdate,
    session: AsyncSession = Depends(get_session),
):
    obj = await session.get(ItemUOM, id)
    if not obj:
        raise HTTPException(status_code=404, detail="ItemUom not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)

    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_item_uom(
    id: int,
    session: AsyncSession = Depends(get_session),
):
    obj = await _get_item_uom_or_404(session, id)

    if bool(obj.is_base):
        raise HTTPException(
            status_code=400,
            detail="基础包装不能删除",
        )

    if await _has_barcode_refs(
        session,
        item_id=int(obj.item_id),
        item_uom_id=int(obj.id),
    ):
        raise HTTPException(
            status_code=409,
            detail="当前包装已绑定条码，不能删除；请先修改条码绑定",
        )

    if await _has_po_line_refs(session, item_uom_id=int(obj.id)):
        raise HTTPException(
            status_code=409,
            detail="当前包装已被采购单引用，不能删除",
        )

    if await _has_receipt_line_refs(session, item_uom_id=int(obj.id)):
        raise HTTPException(
            status_code=409,
            detail="当前包装已被收货记录引用，不能删除",
        )

    need_fallback_default = bool(
        obj.is_purchase_default or obj.is_inbound_default or obj.is_outbound_default
    )

    if need_fallback_default:
        base = await _find_base_uom(
            session,
            item_id=int(obj.item_id),
            exclude_id=int(obj.id),
        )
        if base is None:
            raise HTTPException(
                status_code=409,
                detail="缺少基础包装，无法安全删除当前包装",
            )

        if obj.is_purchase_default:
            base.is_purchase_default = True
        if obj.is_inbound_default:
            base.is_inbound_default = True
        if obj.is_outbound_default:
            base.is_outbound_default = True

    await session.delete(obj)
    await session.commit()
    return {"ok": True}
