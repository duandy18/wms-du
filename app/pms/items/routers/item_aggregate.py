# app/pms/items/routers/item_aggregate.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item_aggregate import ItemAggregateOut, ItemAggregatePayload
from app.pms.items.services.item_owner_aggregate_service import ItemOwnerAggregateService

router = APIRouter(prefix="/items", tags=["items-owner-aggregate"])


def get_item_owner_aggregate_service(db: Session = Depends(get_db)) -> ItemOwnerAggregateService:
    return ItemOwnerAggregateService(db)


def _raise_from_value_error(e: ValueError) -> None:
    detail = str(e)

    if detail == "Item not found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    if (
        detail == "SKU duplicate"
        or "Barcode already exists" in detail
        or "Current item_uom already bound to a barcode" in detail
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("/{item_id}/aggregate", response_model=ItemAggregateOut)
def get_item_aggregate(
    item_id: int,
    service: ItemOwnerAggregateService = Depends(get_item_owner_aggregate_service),
):
    try:
        return service.get_aggregate(item_id=int(item_id))
    except ValueError as e:
        _raise_from_value_error(e)


@router.post("/aggregate", response_model=ItemAggregateOut, status_code=status.HTTP_201_CREATED)
def create_item_aggregate(
    payload: ItemAggregatePayload,
    service: ItemOwnerAggregateService = Depends(get_item_owner_aggregate_service),
):
    try:
        return service.create_aggregate(payload=payload)
    except ValueError as e:
        _raise_from_value_error(e)


@router.put("/{item_id}/aggregate", response_model=ItemAggregateOut)
def replace_item_aggregate(
    item_id: int,
    payload: ItemAggregatePayload,
    service: ItemOwnerAggregateService = Depends(get_item_owner_aggregate_service),
):
    try:
        return service.replace_aggregate(item_id=int(item_id), payload=payload)
    except ValueError as e:
        _raise_from_value_error(e)
