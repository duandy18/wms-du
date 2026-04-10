# app/pms/public/items/routers/item_aggregate_read.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.public.items.contracts.item_aggregate import PublicItemAggregateOut
from app.pms.public.items.services.item_aggregate_read_service import ItemAggregateReadService

router = APIRouter(prefix="/public/items", tags=["pms-public-items"])


def get_item_aggregate_read_service(db: Session = Depends(get_db)) -> ItemAggregateReadService:
    return ItemAggregateReadService(db)


@router.get("/{item_id}/aggregate", response_model=PublicItemAggregateOut, status_code=status.HTTP_200_OK)
def get_public_item_aggregate_by_id(
    item_id: int,
    service: ItemAggregateReadService = Depends(get_item_aggregate_read_service),
) -> PublicItemAggregateOut:
    obj = service.get_aggregate_by_id(item_id=int(item_id))
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return obj
