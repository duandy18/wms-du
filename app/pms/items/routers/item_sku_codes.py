# app/pms/items/routers/item_sku_codes.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item_sku_code import (
    ItemSkuCodeChangePrimary,
    ItemSkuCodeCreate,
    ItemSkuCodeOut,
)
from app.pms.items.services.item_sku_code_service import ItemSkuCodeService


router = APIRouter(prefix="/items/{item_id}/sku-codes", tags=["item-sku-codes"])


def get_item_sku_code_service(db: Session = Depends(get_db)) -> ItemSkuCodeService:
    return ItemSkuCodeService(db)


def _raise_http_from_value_error(e: ValueError) -> None:
    detail = str(e)
    if detail in {"Item not found", "SKU code not found"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if detail in {"SKU code duplicate"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("", response_model=List[ItemSkuCodeOut])
def list_item_sku_codes(
    item_id: int,
    service: ItemSkuCodeService = Depends(get_item_sku_code_service),
):
    try:
        return service.list_codes(item_id=int(item_id))
    except ValueError as e:
        _raise_http_from_value_error(e)


@router.post("", response_model=ItemSkuCodeOut, status_code=status.HTTP_201_CREATED)
def create_item_sku_code(
    item_id: int,
    payload: ItemSkuCodeCreate,
    service: ItemSkuCodeService = Depends(get_item_sku_code_service),
):
    try:
        return service.create_code(
            item_id=int(item_id),
            code=payload.code,
            code_type=payload.code_type,
            is_active=payload.is_active,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            remark=payload.remark,
        )
    except ValueError as e:
        _raise_http_from_value_error(e)


@router.post("/{code_id}/disable", response_model=ItemSkuCodeOut)
def disable_item_sku_code(
    item_id: int,
    code_id: int,
    service: ItemSkuCodeService = Depends(get_item_sku_code_service),
):
    try:
        return service.disable_code(item_id=int(item_id), code_id=int(code_id))
    except ValueError as e:
        _raise_http_from_value_error(e)


@router.post("/{code_id}/enable", response_model=ItemSkuCodeOut)
def enable_item_sku_code(
    item_id: int,
    code_id: int,
    service: ItemSkuCodeService = Depends(get_item_sku_code_service),
):
    try:
        return service.enable_code(item_id=int(item_id), code_id=int(code_id))
    except ValueError as e:
        _raise_http_from_value_error(e)


@router.post("/change-primary", response_model=ItemSkuCodeOut)
def change_primary_item_sku_code(
    item_id: int,
    payload: ItemSkuCodeChangePrimary,
    service: ItemSkuCodeService = Depends(get_item_sku_code_service),
):
    try:
        return service.change_primary(
            item_id=int(item_id),
            code=payload.code,
            remark=payload.remark,
        )
    except ValueError as e:
        _raise_http_from_value_error(e)
