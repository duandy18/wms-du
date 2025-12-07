# app/api/routers/item_barcodes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.item import Item
from app.models.item_barcode import ItemBarcode

router = APIRouter(prefix="/item-barcodes", tags=["item-barcodes"])


# ---------- Pydantic ----------


class ItemBarcodeCreate(BaseModel):
    item_id: int
    barcode: str
    kind: str = "CUSTOM"
    active: bool = True


class ItemBarcodeUpdate(BaseModel):
    """PATCH 更新条码：可用于切主条码/启用/停用/修改类型"""

    barcode: Optional[str] = None
    kind: Optional[str] = None
    active: Optional[bool] = None
    is_primary: Optional[bool] = None


class ItemBarcodeOut(BaseModel):
    id: int
    item_id: int
    barcode: str
    kind: str
    active: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


# ---------- 创建条码 ----------


@router.post("", response_model=ItemBarcodeOut, status_code=status.HTTP_201_CREATED)
def create_barcode(
    body: ItemBarcodeCreate,
    db: Session = Depends(get_db),
):
    item = db.get(Item, body.item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    code = body.barcode.strip()
    if not code:
        raise HTTPException(400, "barcode is required")

    # 全局去重
    exists = db.execute(select(ItemBarcode).where(ItemBarcode.barcode == code)).scalars().first()
    if exists:
        raise HTTPException(409, "Barcode already exists")

    obj = ItemBarcode(
        item_id=body.item_id,
        barcode=code,
        kind=body.kind.strip() or "CUSTOM",
        active=bool(body.active),
        is_primary=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------- 按 ItemId 读取条码 ----------


@router.get("/item/{item_id}", response_model=List[ItemBarcodeOut])
def list_barcodes_for_item(item_id: int, db: Session = Depends(get_db)):
    if item_id <= 0:
        raise HTTPException(400, "invalid item_id")

    rows = (
        db.execute(
            select(ItemBarcode).where(ItemBarcode.item_id == item_id).order_by(ItemBarcode.id.asc())
        )
        .scalars()
        .all()
    )
    return list(rows)


# ---------- 设置主条码 ----------


@router.post("/{id}/set-primary", response_model=ItemBarcodeOut)
def set_primary(id: int, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    # 取消当前 item 的所有主条码
    db.execute(
        update(ItemBarcode).where(ItemBarcode.item_id == bc.item_id).values(is_primary=False)
    )
    # 设置新主条码
    bc.is_primary = True
    db.commit()
    db.refresh(bc)
    return bc


# ---------- PATCH 更新条码 ----------


@router.patch("/{id}", response_model=ItemBarcodeOut)
def update_barcode(id: int, body: ItemBarcodeUpdate, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    # 不能修改 barcode 本身（全局唯一）
    if body.kind is not None:
        bc.kind = body.kind

    if body.active is not None:
        bc.active = bool(body.active)

    if body.is_primary is True:
        # 等价于 set_primary
        db.execute(
            update(ItemBarcode).where(ItemBarcode.item_id == bc.item_id).values(is_primary=False)
        )
        bc.is_primary = True

    db.commit()
    db.refresh(bc)
    return bc


# ---------- 删除条码 ----------


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_barcode(id: int, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    db.delete(bc)
    db.commit()
    return None
