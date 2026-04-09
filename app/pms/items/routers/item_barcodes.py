# app/pms/items/routers/item_barcodes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.item_barcode import ItemBarcode
from app.models.item_uom import ItemUOM

router = APIRouter(prefix="/item-barcodes", tags=["item-barcodes"])


def _normalize_symbology(v: str | None) -> str:
    s = (v or "").strip().upper()
    return s or "CUSTOM"


def _get_item_uom_or_404(db: Session, item_uom_id: int) -> ItemUOM:
    obj = db.get(ItemUOM, int(item_uom_id))
    if not obj:
        raise HTTPException(404, "ItemUom not found")
    return obj


class ItemBarcodeCreate(BaseModel):
    item_uom_id: int
    barcode: str
    symbology: str = "CUSTOM"
    active: bool = True


class ItemBarcodeUpdate(BaseModel):
    """PATCH 更新条码：可用于切主条码/启用/停用/修改码制/修改条码值"""

    barcode: Optional[str] = None
    symbology: Optional[str] = None
    active: Optional[bool] = None
    is_primary: Optional[bool] = None


class ItemBarcodeOut(BaseModel):
    id: int
    item_id: int
    item_uom_id: int
    barcode: str
    symbology: str
    active: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ItemBarcodeOut, status_code=status.HTTP_201_CREATED)
def create_barcode(
    body: ItemBarcodeCreate,
    db: Session = Depends(get_db),
):
    uom = _get_item_uom_or_404(db, body.item_uom_id)

    code = body.barcode.strip()
    if not code:
        raise HTTPException(400, "barcode is required")

    exists = db.execute(select(ItemBarcode).where(ItemBarcode.barcode == code)).scalars().first()
    if exists:
        raise HTTPException(409, "Barcode already exists")

    obj = ItemBarcode(
        item_id=int(uom.item_id),
        item_uom_id=int(uom.id),
        barcode=code,
        symbology=_normalize_symbology(body.symbology),
        active=bool(body.active),
        is_primary=False,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/by-items", response_model=List[ItemBarcodeOut])
def list_barcodes_for_items(
    item_id: List[int] = Query(..., description="item_id 可重复：item_id=1&item_id=2"),
    active_only: bool = Query(True, description="默认只返回 active=true"),
    db: Session = Depends(get_db),
):
    ids = [int(x) for x in item_id if int(x) > 0]
    if not ids:
        return []

    stmt = select(ItemBarcode).where(ItemBarcode.item_id.in_(ids))
    if active_only:
        stmt = stmt.where(ItemBarcode.active.is_(True))

    rows = db.execute(stmt.order_by(ItemBarcode.item_id.asc(), ItemBarcode.id.asc())).scalars().all()
    return list(rows)


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


@router.post("/{id}/set-primary", response_model=ItemBarcodeOut)
def set_primary(id: int, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    db.execute(
        update(ItemBarcode).where(ItemBarcode.item_id == bc.item_id).values(is_primary=False)
    )
    bc.active = True
    bc.is_primary = True
    db.commit()
    db.refresh(bc)
    return bc


@router.post("/{id}/primary", status_code=status.HTTP_204_NO_CONTENT)
def set_primary_compat(id: int, db: Session = Depends(get_db)):
    _ = set_primary(id, db)
    return None


@router.patch("/{id}", response_model=ItemBarcodeOut)
def update_barcode(id: int, body: ItemBarcodeUpdate, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    if body.barcode is not None:
        code = body.barcode.strip()
        if not code:
            raise HTTPException(400, "barcode is required")
        exists = (
            db.execute(
                select(ItemBarcode).where(
                    ItemBarcode.barcode == code,
                    ItemBarcode.id != bc.id,
                )
            )
            .scalars()
            .first()
        )
        if exists:
            raise HTTPException(409, "Barcode already exists")
        bc.barcode = code

    if body.symbology is not None:
        bc.symbology = _normalize_symbology(body.symbology)

    if body.active is not None:
        next_active = bool(body.active)
        if (body.is_primary is True) or (body.is_primary is None and bc.is_primary and not next_active):
            raise HTTPException(400, "primary barcode must be active")
        bc.active = next_active

    if body.is_primary is True:
        db.execute(
            update(ItemBarcode).where(ItemBarcode.item_id == bc.item_id).values(is_primary=False)
        )
        bc.active = True
        bc.is_primary = True
    elif body.is_primary is False:
        bc.is_primary = False

    db.commit()
    db.refresh(bc)
    return bc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_barcode(id: int, db: Session = Depends(get_db)):
    bc = db.get(ItemBarcode, id)
    if not bc:
        raise HTTPException(404, "Barcode not found")

    db.delete(bc)
    db.commit()
    return None
