# app/api/routers/items_by_id.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.schemas.item import ItemCreateById, ItemOut
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items-by-id"])


def get_item_service(db: Session = Depends(get_db)):
    return ItemService(db)


@router.post("/by-id", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item_by_id(
    body: ItemCreateById,
    item_service: ItemService = Depends(get_item_service),
):
    try:
        obj = item_service.create_item_by_id(
            id=body.id,
            sku=body.sku,
            name=body.name,
            description=body.description,
        )
        return obj
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
