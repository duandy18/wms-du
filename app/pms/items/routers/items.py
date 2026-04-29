# app/pms/items/routers/items.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item import ItemCreate, ItemOut, ItemUpdate
from app.pms.items.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)


def _normalize_policy(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    return s if s else None


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
            brand_id=item_in.brand_id,
            category_id=item_in.category_id,
            enabled=item_in.enabled,
            supplier_id=item_in.supplier_id,
            lot_source_policy=_normalize_policy(item_in.lot_source_policy) or "SUPPLIER_ONLY",
            expiry_policy=_normalize_policy(item_in.expiry_policy) or "NONE",
            derivation_allowed=True if item_in.derivation_allowed is None else bool(item_in.derivation_allowed),
            uom_governance_enabled=(
                False if item_in.uom_governance_enabled is None else bool(item_in.uom_governance_enabled)
            ),
            shelf_life_value=item_in.shelf_life_value,
            shelf_life_unit=item_in.shelf_life_unit,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "SKU duplicate":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("", response_model=List[ItemOut])
def get_all_items(
    supplier_id: Optional[int] = Query(None, ge=1, description="按供应商过滤（采购单创建/收货用）"),
    enabled: Optional[bool] = Query(None, description="按启用状态过滤（enabled=true 只取启用商品）"),
    q: Optional[str] = Query(None, description="关键词搜索（命中 sku/name/primary_barcode/id；大小写不敏感）"),
    limit: Optional[int] = Query(None, ge=1, le=200, description="限制返回条数（默认 50，最大 200）"),
    item_service: ItemService = Depends(get_item_service),
):
    return item_service.get_items(
        supplier_id=supplier_id,
        enabled=enabled,
        q=q,
        limit=limit,
    )


@router.get("/sku/{sku}", response_model=ItemOut)
def get_item_by_sku(sku: str, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_sku(sku)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


@router.get("/{id}", response_model=ItemOut)
def get_item_by_id(id: int, item_service: ItemService = Depends(get_item_service)):
    obj = item_service.get_item_by_id(id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj


@router.patch("/{id}", response_model=ItemOut)
def update_item(
    id: int,
    item_in: ItemUpdate,
    item_service: ItemService = Depends(get_item_service),
):
    data = item_in.model_dump(exclude_unset=True)
    fields_set = set(item_in.model_fields_set)

    try:
        return item_service.update_item(
            id=id,
            name=data.get("name"),
            name_set=("name" in fields_set),
            spec=data.get("spec"),
            spec_set=("spec" in fields_set),
            enabled=data.get("enabled"),
            enabled_set=("enabled" in fields_set),
            supplier_id=data.get("supplier_id"),
            supplier_id_set=("supplier_id" in fields_set),
            lot_source_policy=(
                _normalize_policy(data.get("lot_source_policy")) if "lot_source_policy" in fields_set else None
            ),
            lot_source_policy_set=("lot_source_policy" in fields_set),
            expiry_policy=(
                _normalize_policy(data.get("expiry_policy")) if "expiry_policy" in fields_set else None
            ),
            expiry_policy_set=("expiry_policy" in fields_set),
            derivation_allowed=data.get("derivation_allowed"),
            derivation_allowed_set=("derivation_allowed" in fields_set),
            uom_governance_enabled=data.get("uom_governance_enabled"),
            uom_governance_enabled_set=("uom_governance_enabled" in fields_set),
            shelf_life_value=data.get("shelf_life_value"),
            shelf_life_value_set=("shelf_life_value" in fields_set),
            shelf_life_unit=data.get("shelf_life_unit"),
            shelf_life_unit_set=("shelf_life_unit" in fields_set),
            brand_id=data.get("brand_id"),
            brand_id_set=("brand_id" in fields_set),
            category_id=data.get("category_id"),
            category_id_set=("category_id" in fields_set),
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Item not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
