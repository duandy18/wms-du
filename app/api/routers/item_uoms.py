from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_session
from app.models.item_uom import ItemUOM
from app.schemas.item_uom import (
    ItemUomCreate,
    ItemUomUpdate,
    ItemUomOut,
)

router = APIRouter(prefix="/item-uoms", tags=["item-uoms"])


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


# ✅ 批量读取（避免 N+1）
# IMPORTANT: 必须放在 "/{id}" 路由之前，避免被 path param 吃掉导致 GET 405
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


@router.delete("/{id}")
async def delete_item_uom(
    id: int,
    session: AsyncSession = Depends(get_session),
):
    obj = await session.get(ItemUOM, id)
    if not obj:
        raise HTTPException(status_code=404, detail="ItemUom not found")

    await session.delete(obj)
    await session.commit()
    return {"ok": True}
