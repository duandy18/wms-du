# app/api/inventory.py

from collections import defaultdict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.inventory import InventoryMovement, MovementType
from app.models.items import Item
from app.models.locations import Location
from app.schemas.inventory import (
    InventoryMovementCreate,
    InventoryMovementOut,
    StockOnHandOut,
)

router = APIRouter()


def get_stock_summary(db: Session) -> defaultdict[tuple[str, str], int]:
    """
    计算每个库位上每个物料的当前库存总量，并返回一个字典。
    """
    stock_summary = defaultdict(int)
    movements = db.query(InventoryMovement).all()
    for move in movements:
        if move.movement_type == MovementType.RECEIPT:
            stock_summary[(move.item_sku, move.to_location_id)] += move.quantity
        elif move.movement_type == MovementType.SHIPMENT:
            stock_summary[(move.item_sku, move.from_location_id)] -= move.quantity
        elif move.movement_type == MovementType.TRANSFER:
            stock_summary[(move.item_sku, move.from_location_id)] -= move.quantity
            stock_summary[(move.item_sku, move.to_location_id)] += move.quantity
    return stock_summary


@router.post(
    "/inventory/movements",
    response_model=InventoryMovementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_movement(movement_in: InventoryMovementCreate, db: Session = Depends(get_db)):
    """
    创建一个新的库存流水记录。
    """
    item = db.query(Item).filter(Item.sku == movement_in.item_sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if movement_in.from_location_id:
        from_loc = db.query(Location).filter(Location.id == movement_in.from_location_id).first()
        if not from_loc:
            raise HTTPException(status_code=404, detail="From location not found")

    if movement_in.to_location_id:
        to_loc = db.query(Location).filter(Location.id == movement_in.to_location_id).first()
        if not to_loc:
            raise HTTPException(status_code=404, detail="To location not found")

    db_movement = InventoryMovement(**movement_in.model_dump())
    db_movement.id = str(uuid4())
    db.add(db_movement)
    db.commit()
    db.refresh(db_movement)
    return db_movement


@router.get("/inventory/movements", response_model=list[InventoryMovementOut])
def get_all_inventory_movements(db: Session = Depends(get_db)):
    """
    获取所有库存流水记录的列表。
    """
    return db.query(InventoryMovement).all()


@router.get("/inventory/movements/by_item/{item_sku}", response_model=list[InventoryMovementOut])
def get_movements_by_item(item_sku: str, db: Session = Depends(get_db)):
    """
    通过物料 SKU 获取其所有库存流水记录。
    """
    return db.query(InventoryMovement).filter(InventoryMovement.item_sku == item_sku).all()


@router.get("/inventory/stock_on_hand", response_model=list[StockOnHandOut])
def get_stock_on_hand(db: Session = Depends(get_db)):
    """
    获取每个库位上每个物料的当前库存总量。
    """
    stock_summary: defaultdict[tuple[str, str], int] = get_stock_summary(db)

    result = []
    for (sku, loc_id), qty in stock_summary.items():
        if qty > 0:
            result.append(StockOnHandOut(item_sku=sku, location_id=loc_id, quantity=qty))

    return result
