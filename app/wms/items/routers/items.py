# app/wms/items/routers/items.py
from __future__ import annotations

import inspect
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.wms.items.contracts.item import ItemCreate, ItemOut, ItemUpdate, NextSkuOut
from app.wms.items.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    return ItemService(db)


def _is_required(policy: Optional[str]) -> bool:
    return str(policy or "").upper() == "REQUIRED"


def _normalize_expiry_policy(expiry_policy: Optional[str]) -> Optional[str]:
    s = str(expiry_policy or "").strip().upper()
    return s if s else None


def _derive_expiry_policy_from_legacy_flag(legacy_has_shelf_life: Optional[bool]) -> str:
    """
    Legacy/Input 兼容：
    - 旧客户端可能只传 has_shelf_life（镜像字段）
    - 新世界观真相源是 expiry_policy
    这里仅用于“当 expiry_policy 缺省时”的兜底推导，避免违反 DB CHECK。
    """
    return "REQUIRED" if bool(legacy_has_shelf_life) else "NONE"


def _call_create_item_compat(item_service: ItemService, **kwargs):
    sig = inspect.signature(item_service.create_item)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    return item_service.create_item(**filtered)


def _call_update_item_compat(item_service: ItemService, **kwargs):
    sig = inspect.signature(item_service.update_item)
    accepted = set(sig.parameters.keys())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    return item_service.update_item(**filtered)


@router.post("/sku/next", response_model=NextSkuOut)
def next_sku(item_service: ItemService = Depends(get_item_service)):
    return NextSkuOut(sku=item_service.next_sku())


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    item_in: ItemCreate,
    item_service: ItemService = Depends(get_item_service),
):
    try:
        exp_policy_norm = _normalize_expiry_policy(item_in.expiry_policy)
        expiry_policy = exp_policy_norm or _derive_expiry_policy_from_legacy_flag(item_in.has_shelf_life)

        lot_source_policy = item_in.lot_source_policy or "SUPPLIER_ONLY"
        derivation_allowed = True if item_in.derivation_allowed is None else bool(item_in.derivation_allowed)
        uom_governance_enabled = False if item_in.uom_governance_enabled is None else bool(item_in.uom_governance_enabled)

        has_shelf_life = _is_required(expiry_policy)

        return _call_create_item_compat(
            item_service,
            name=item_in.name,
            spec=item_in.spec,
            barcode=item_in.barcode,
            brand=item_in.brand,
            category=item_in.category,
            enabled=item_in.enabled,
            supplier_id=item_in.supplier_id,
            lot_source_policy=lot_source_policy,
            expiry_policy=expiry_policy,
            derivation_allowed=derivation_allowed,
            uom_governance_enabled=uom_governance_enabled,
            has_shelf_life=has_shelf_life,
            shelf_life_value=item_in.shelf_life_value,
            shelf_life_unit=item_in.shelf_life_unit,
            weight_kg=item_in.weight_kg,
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


@router.post("/{id}/test:enable", response_model=ItemOut)
def enable_test_item(id: int, item_service: ItemService = Depends(get_item_service)):
    try:
        return item_service.enable_item_test_flag(item_id=id, set_code="DEFAULT")
    except ValueError as e:
        detail = str(e)
        if detail == "Item not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        if detail.startswith("测试集合不存在："):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post("/{id}/test:disable", response_model=ItemOut)
def disable_test_item(id: int, item_service: ItemService = Depends(get_item_service)):
    try:
        return item_service.disable_item_test_flag(item_id=id, set_code="DEFAULT")
    except ValueError as e:
        detail = str(e)
        if detail == "Item not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        if detail.startswith("测试集合不存在："):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.patch("/{id}", response_model=ItemOut)
def update_item(
    id: int,
    item_in: ItemUpdate,
    item_service: ItemService = Depends(get_item_service),
):
    data = item_in.model_dump(exclude_unset=True)

    if "sku" in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SKU is immutable and managed by backend",
        )

    if "barcode" in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="barcode is managed by /item-barcodes (set primary there)",
        )

    expiry_policy = _normalize_expiry_policy(data.get("expiry_policy"))
    if expiry_policy is None and "has_shelf_life" in data and data.get("has_shelf_life") is not None:
        expiry_policy = _derive_expiry_policy_from_legacy_flag(bool(data.get("has_shelf_life")))

    lot_source_policy = data.get("lot_source_policy")
    derivation_allowed = data.get("derivation_allowed")
    uom_governance_enabled = data.get("uom_governance_enabled")

    has_shelf_life = data.get("has_shelf_life")
    if expiry_policy is not None:
        has_shelf_life = _is_required(expiry_policy)

    try:
        return _call_update_item_compat(
            item_service,
            id=id,
            name=data.get("name"),
            spec=data.get("spec"),
            enabled=data.get("enabled"),
            supplier_id=data.get("supplier_id"),
            lot_source_policy=lot_source_policy,
            expiry_policy=expiry_policy,
            derivation_allowed=derivation_allowed,
            uom_governance_enabled=uom_governance_enabled,
            has_shelf_life=has_shelf_life,
            shelf_life_value=data.get("shelf_life_value"),
            shelf_life_unit=data.get("shelf_life_unit"),
            weight_kg=data.get("weight_kg"),
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
