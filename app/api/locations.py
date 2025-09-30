# app/api/locations.py
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.locations import Location, Warehouse
from app.schemas.locations import LocationCreate, LocationOut, WarehouseCreate, WarehouseOut

router = APIRouter()

# --- 仓库（Warehouse）路由 ---


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(warehouse_in: WarehouseCreate, db: Session = Depends(get_db)):
    """
    创建一个新的仓库。
    """
    db_warehouse = Warehouse(**warehouse_in.model_dump())
    db_warehouse.id = str(uuid4())
    db.add(db_warehouse)
    db.commit()
    db.refresh(db_warehouse)
    return db_warehouse


@router.get("/warehouses", response_model=list[WarehouseOut])
def get_all_warehouses(db: Session = Depends(get_db)):
    """
    获取所有仓库的列表。
    """
    return db.query(Warehouse).all()


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseOut)
def get_warehouse(warehouse_id: str, db: Session = Depends(get_db)):
    """
    通过ID获取单个仓库。
    """
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse


# --- 库位（Location）路由 ---


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(location_in: LocationCreate, db: Session = Depends(get_db)):
    """
    创建一个新的库位。
    """
    # 检查父仓库是否存在
    warehouse = db.query(Warehouse).filter(Warehouse.id == location_in.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Parent warehouse not found")

    db_location = Location(**location_in.model_dump())
    db_location.id = str(uuid4())
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location


@router.get("/locations", response_model=list[LocationOut])
def get_all_locations(db: Session = Depends(get_db)):
    """
    获取所有库位的列表。
    """
    return db.query(Location).all()


@router.get("/locations/{location_id}", response_model=LocationOut)
def get_location(location_id: str, db: Session = Depends(get_db)):
    """
    通过ID获取单个库位。
    """
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location
