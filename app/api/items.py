# app/api/items.py
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.items import Item
from app.schemas.items import ItemCreate, ItemOut

router = APIRouter()


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(item_in: ItemCreate, db: Session = Depends(get_db)):
    """
    创建一个新的物料。
    """
    # 检查 SKU 是否已存在
    existing_item = db.query(Item).filter(Item.sku == item_in.sku).first()
    if existing_item:
        raise HTTPException(status_code=400, detail="SKU already registered")

    db_item = Item(**item_in.model_dump())
    db_item.id = str(uuid4())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/items", response_model=list[ItemOut])
def get_all_items(db: Session = Depends(get_db)):
    """
    获取所有物料的列表。
    """
    return db.query(Item).all()


@router.get("/items/{item_sku}", response_model=ItemOut)
def get_item_by_sku(item_sku: str, db: Session = Depends(get_db)):
    """
    通过 SKU 获取单个物料。
    """
    item = db.query(Item).filter(Item.sku == item_sku).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
