# app/pms/items/routers/item_barcodes.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.item import Item
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


def _ensure_item_uom_barcode_vacant(
    db: Session,
    *,
    item_id: int,
    item_uom_id: int,
    exclude_barcode_id: int | None = None,
) -> None:
    stmt = select(ItemBarcode.id).where(
        ItemBarcode.item_id == int(item_id),
        ItemBarcode.item_uom_id == int(item_uom_id),
    )
    if exclude_barcode_id is not None:
        stmt = stmt.where(ItemBarcode.id != int(exclude_barcode_id))

    exists = db.execute(stmt.limit(1)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(409, "Current item_uom already bound to a barcode")


class ItemBarcodeCreate(BaseModel):
    item_uom_id: int
    barcode: str
    symbology: str = "CUSTOM"
    active: bool = True


class ItemBarcodeUpdate(BaseModel):
    """PATCH 更新条码：可用于改绑包装 / 改条码 / 改码制 / 切主条码"""

    item_uom_id: Optional[int] = None
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


class ItemBarcodeCompositeRow(BaseModel):
    """
    商品条码页 owner 复合只读行：
    - 一行 = 一个商品 + 一个单位 + 一条码
    - 页面用它直接渲染，不再让前端分别请求 /item-barcodes 与 /item-uoms 后自行 join
    """

    barcode_id: int
    item_id: int
    item_uom_id: int

    sku: str
    item_name: str

    uom: str
    display_name: Optional[str]
    ratio_to_base: int
    is_base: bool
    is_purchase_default: bool

    barcode: str
    symbology: str
    is_primary: bool
    active: bool
    updated_at: datetime


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

    _ensure_item_uom_barcode_vacant(
        db,
        item_id=int(uom.item_id),
        item_uom_id=int(uom.id),
    )

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


@router.get("/item/{item_id}/rows", response_model=List[ItemBarcodeCompositeRow])
def list_barcode_rows_for_item(
    item_id: int,
    active_only: bool = Query(False, description="true 时仅返回 active=true 的条码行"),
    db: Session = Depends(get_db),
):
    """
    Owner 读模型：
    - 返回“一个商品、一个单位、一行条码”的复合结果
    - 供 PMS 商品条码页直接渲染当前商品条码表
    """
    if item_id <= 0:
        raise HTTPException(400, "invalid item_id")

    stmt = (
        select(ItemBarcode, ItemUOM, Item)
        .join(
            ItemUOM,
            (ItemUOM.id == ItemBarcode.item_uom_id)
            & (ItemUOM.item_id == ItemBarcode.item_id),
        )
        .join(Item, Item.id == ItemBarcode.item_id)
        .where(ItemBarcode.item_id == item_id)
    )

    if active_only:
        stmt = stmt.where(ItemBarcode.active.is_(True))

    rows = db.execute(
        stmt.order_by(
            ItemUOM.ratio_to_base.asc(),
            ItemUOM.id.asc(),
            ItemBarcode.id.asc(),
        )
    ).all()

    return [
        ItemBarcodeCompositeRow(
            barcode_id=int(bc.id),
            item_id=int(item.id),
            item_uom_id=int(uom.id),
            sku=str(item.sku),
            item_name=str(item.name),
            uom=str(uom.uom),
            display_name=str(uom.display_name).strip() if uom.display_name is not None else None,
            ratio_to_base=int(uom.ratio_to_base),
            is_base=bool(uom.is_base),
            is_purchase_default=bool(uom.is_purchase_default),
            barcode=str(bc.barcode),
            symbology=str(bc.symbology),
            is_primary=bool(bc.is_primary),
            active=bool(bc.active),
            updated_at=bc.updated_at,
        )
        for bc, uom, item in rows
    ]


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

    if body.item_uom_id is not None:
        target_uom = _get_item_uom_or_404(db, body.item_uom_id)
        if int(target_uom.item_id) != int(bc.item_id):
            raise HTTPException(400, "item_uom_id does not belong to current item")

        _ensure_item_uom_barcode_vacant(
            db,
            item_id=int(bc.item_id),
            item_uom_id=int(target_uom.id),
            exclude_barcode_id=int(bc.id),
        )
        bc.item_uom_id = int(target_uom.id)

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
