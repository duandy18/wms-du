# app/api/routers/items.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.item import ItemCreate, ItemOut, ItemUpdate, NextSkuOut
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)


# ===========================
# SKU 后端权威发号
# ===========================
@router.post("/sku/next", response_model=NextSkuOut)
def next_sku(item_service: ItemService = Depends(get_item_service)):
    """
    返回下一个 SKU：
    - AKT-000001...
    - 并发安全
    - 不创建 item
    """
    return NextSkuOut(sku=item_service.next_sku())


# ===========================
# Create Item（统一标准：后端生成 SKU）
# ===========================
@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    item_in: ItemCreate,
    item_service: ItemService = Depends(get_item_service),
):
    try:
        # SKU 永远由后端生成；不接受前端/脚本传入
        return item_service.create_item(
            name=item_in.name,
            spec=item_in.spec,
            uom=item_in.uom,
            barcode=item_in.barcode,
            brand=item_in.brand,
            category=item_in.category,
            enabled=item_in.enabled,
            supplier_id=item_in.supplier_id,
            has_shelf_life=item_in.has_shelf_life,
            shelf_life_value=item_in.shelf_life_value,
            shelf_life_unit=item_in.shelf_life_unit,
            weight_kg=item_in.weight_kg,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "SKU duplicate":
            # 理论上不会发生（序列发号），保留防御
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ===========================
# Query
# ===========================
@router.get("", response_model=List[ItemOut])
def get_all_items(
    supplier_id: Optional[int] = Query(
        None,
        ge=1,
        description="按供应商过滤（采购单创建/收货用）",
    ),
    enabled: Optional[bool] = Query(
        None,
        description="按启用状态过滤（enabled=true 只取启用商品）",
    ),
    item_service: ItemService = Depends(get_item_service),
):
    # ✅ 向后兼容：不传参数时等价于旧行为（返回全量）
    return item_service.get_items(supplier_id=supplier_id, enabled=enabled)


@router.get("/{id}", response_model=ItemOut)
def get_item_by_id(id: int, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_id(id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


@router.get("/sku/{sku}", response_model=ItemOut)
def get_item_by_sku(sku: str, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_sku(sku)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


# ===========================
# Update（不允许改 SKU）
# ===========================
@router.patch("/{id}", response_model=ItemOut)
def update_item(
    id: int,
    item_in: ItemUpdate,
    item_service: ItemService = Depends(get_item_service),
):
    data = item_in.model_dump(exclude_unset=True)

    # 强制禁止通过 Update 修改 SKU（防止“后门改码”）
    if "sku" in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU is immutable and managed by backend",
        )

    try:
        return item_service.update_item(
            id=id,
            name=data.get("name"),
            spec=data.get("spec"),
            uom=data.get("uom"),
            enabled=data.get("enabled"),
            supplier_id=data.get("supplier_id"),
            has_shelf_life=data.get("has_shelf_life"),
            shelf_life_value=data.get("shelf_life_value"),
            shelf_life_unit=data.get("shelf_life_unit"),
            weight_kg=data.get("weight_kg"),
            # ✅ brand/category：需要区分“未提供” vs “显式置空(null)”
            brand=data.get("brand"),
            category=data.get("category"),
            brand_set=("brand" in data),
            category_set=("category" in data),
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Item not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
