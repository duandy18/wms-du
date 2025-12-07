# app/api/routers/items.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.item import ItemCreate, ItemCreateById, ItemOut, ItemUpdate
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)


# ---------------------------------------------------------
# 1) 创建商品
# ---------------------------------------------------------
@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    item_in: ItemCreate,
    item_service: ItemService = Depends(get_item_service),
):
    try:
        return item_service.create_item(
            sku=item_in.sku,
            name=item_in.name,
            spec=item_in.spec,
            uom=item_in.uom,
            enabled=item_in.enabled,
            supplier_id=item_in.supplier_id,
            shelf_life_value=item_in.shelf_life_value,
            shelf_life_unit=item_in.shelf_life_unit,
            # ⭐ 新增：单件净重（kg）
            weight_kg=item_in.weight_kg,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "SKU duplicate":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ---------------------------------------------------------
# 2) 按 ID 创建
# ---------------------------------------------------------
@router.post("/by-id", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item_by_id(
    item_in: ItemCreateById,
    item_service: ItemService = Depends(get_item_service),
):
    try:
        return item_service.create_item_by_id(
            id=item_in.id,
            sku=item_in.sku,
            name=item_in.name,
            spec=item_in.spec,
            uom=item_in.uom,
            enabled=item_in.enabled,
            supplier_id=item_in.supplier_id,
            shelf_life_value=item_in.shelf_life_value,
            shelf_life_unit=item_in.shelf_life_unit,
            # ⭐ 新增
            weight_kg=item_in.weight_kg,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------
# 3) 查询
# ---------------------------------------------------------
@router.get("", response_model=List[ItemOut])
def get_all_items(item_service: ItemService = Depends(get_item_service)):
    return item_service.get_all_items()


@router.get("/id/{id}", response_model=ItemOut)
def get_item_by_id(id: int, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_id(id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


@router.get("/{sku}", response_model=ItemOut)
def get_item_by_sku(sku: str, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_sku(sku)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


# ---------------------------------------------------------
# 4) 更新
# ---------------------------------------------------------
@router.patch("/{id}", response_model=ItemOut)
def update_item(
    id: int,
    item_in: ItemUpdate,
    item_service: ItemService = Depends(get_item_service),
):
    data = item_in.model_dump(exclude_unset=True)

    try:
        return item_service.update_item(
            id=id,
            name=data.get("name"),
            spec=data.get("spec"),
            uom=data.get("uom"),
            enabled=data.get("enabled"),
            supplier_id=data.get("supplier_id"),
            shelf_life_value=data.get("shelf_life_value"),
            shelf_life_unit=data.get("shelf_life_unit"),
            # ⭐ 新增
            weight_kg=data.get("weight_kg"),
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Item not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
