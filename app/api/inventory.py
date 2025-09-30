# app/api/inventory.py
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.inventory import InventoryMovement
from app.models.items import Item
from app.models.locations import Location
from app.schemas.inventory import InventoryMovementCreate, InventoryMovementOut

router = APIRouter()


@router.post(
    "/inventory/movements", response_model=InventoryMovementOut, status_code=status.HTTP_201_CREATED
)
def create_inventory_movement(movement_in: InventoryMovementCreate, db: Session = Depends(get_db)):
    """
    创建一个新的库存流水记录。
    """
    # 验证物料 SKU 是否存在
    item = db.query(Item).filter(Item.sku == movement_in.item_sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 验证来源库位是否存在 (如果提供了)
    if movement_in.from_location_id:
        from_loc = db.query(Location).filter(Location.id == movement_in.from_location_id).first()
        if not from_loc:
            raise HTTPException(status_code=404, detail="From location not found")

    # 验证目标库位是否存在 (如果提供了)
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
