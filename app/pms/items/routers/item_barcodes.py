# app/pms/items/routers/item_barcodes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.items.contracts.item_uom import ItemUomBarcodeRowOut
from app.pms.items.repos.item_barcode_repo import (
    clear_primary_flags_for_item,
    create_item_barcode,
    delete_item_barcode,
    get_item_barcode_by_code,
    get_item_barcode_by_id,
    get_item_uom_by_id,
    has_barcode_bound_to_item_uom,
    list_barcode_row_sources_for_item,
    list_item_barcodes_by_item_id,
    list_item_barcodes_by_item_ids,
    refresh_item_barcode,
    update_item_barcode_fields,
)

router = APIRouter(prefix="/item-barcodes", tags=["item-barcodes"])


def _normalize_symbology(v: str | None) -> str:
    s = (v or "").strip().upper()
    return s or "CUSTOM"


def _get_item_uom_or_404(db: Session, item_uom_id: int):
    obj = get_item_uom_by_id(db, int(item_uom_id))
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
    exists = has_barcode_bound_to_item_uom(
        db,
        item_id=int(item_id),
        item_uom_id=int(item_uom_id),
        exclude_barcode_id=exclude_barcode_id,
    )
    if exists:
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


class ItemBarcodeCompositeRow(ItemUomBarcodeRowOut):
    """
    商品条码页 owner 复合只读行：
    - 继承 item_uoms owner 复合读模型，包装字段以 item_uoms 合同为唯一来源
    - 当前接口只返回已绑定条码的行，因此条码字段在这里收紧为必填
    """

    barcode_id: int
    barcode: str
    symbology: str
    is_primary: bool
    active: bool


@router.post("", response_model=ItemBarcodeOut, status_code=status.HTTP_201_CREATED)
def create_barcode(
    body: ItemBarcodeCreate,
    db: Session = Depends(get_db),
):
    uom = _get_item_uom_or_404(db, body.item_uom_id)

    code = body.barcode.strip()
    if not code:
        raise HTTPException(400, "barcode is required")

    exists = get_item_barcode_by_code(db, barcode=code)
    if exists:
        raise HTTPException(409, "Barcode already exists")

    _ensure_item_uom_barcode_vacant(
        db,
        item_id=int(uom.item_id),
        item_uom_id=int(uom.id),
    )

    obj = create_item_barcode(
        db,
        item_id=int(uom.item_id),
        item_uom_id=int(uom.id),
        barcode=code,
        symbology=_normalize_symbology(body.symbology),
        active=bool(body.active),
        is_primary=False,
    )
    db.commit()
    refresh_item_barcode(db, obj)
    return obj


@router.get("/by-items", response_model=List[ItemBarcodeOut])
def list_barcodes_for_items(
    item_id: List[int] = Query(..., description="item_id 可重复：item_id=1&item_id=2"),
    active_only: bool = Query(True, description="默认只返回 active=true"),
    db: Session = Depends(get_db),
):
    rows = list_item_barcodes_by_item_ids(
        db,
        item_ids=item_id,
        active_only=bool(active_only),
    )
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

    rows = list_barcode_row_sources_for_item(
        db,
        item_id=int(item_id),
        active_only=bool(active_only),
    )

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
            net_weight_kg=float(uom.net_weight_kg) if uom.net_weight_kg is not None else None,
            is_base=bool(uom.is_base),
            is_purchase_default=bool(uom.is_purchase_default),
            is_inbound_default=bool(uom.is_inbound_default),
            is_outbound_default=bool(uom.is_outbound_default),
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

    rows = list_item_barcodes_by_item_id(
        db,
        item_id=int(item_id),
        active_only=None,
    )
    return list(rows)


@router.post("/{id}/set-primary", response_model=ItemBarcodeOut)
def set_primary(id: int, db: Session = Depends(get_db)):
    bc = get_item_barcode_by_id(db, int(id))
    if not bc:
        raise HTTPException(404, "Barcode not found")

    clear_primary_flags_for_item(db, item_id=int(bc.item_id))
    update_item_barcode_fields(
        bc,
        active=True,
        is_primary=True,
    )
    db.commit()
    refresh_item_barcode(db, bc)
    return bc


@router.patch("/{id}", response_model=ItemBarcodeOut)
def update_barcode(id: int, body: ItemBarcodeUpdate, db: Session = Depends(get_db)):
    bc = get_item_barcode_by_id(db, int(id))
    if not bc:
        raise HTTPException(404, "Barcode not found")

    next_item_uom_id: int | None = None
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
        next_item_uom_id = int(target_uom.id)

    next_barcode: str | None = None
    if body.barcode is not None:
        code = body.barcode.strip()
        if not code:
            raise HTTPException(400, "barcode is required")
        exists = get_item_barcode_by_code(
            db,
            barcode=code,
            exclude_id=int(bc.id),
        )
        if exists:
            raise HTTPException(409, "Barcode already exists")
        next_barcode = code

    next_symbology = _normalize_symbology(body.symbology) if body.symbology is not None else None

    if body.active is not None:
        next_active = bool(body.active)
        if (body.is_primary is True) or (body.is_primary is None and bc.is_primary and not next_active):
            raise HTTPException(400, "primary barcode must be active")
    else:
        next_active = None

    if body.is_primary is True:
        clear_primary_flags_for_item(db, item_id=int(bc.item_id))
        # 主条码必须 active
        next_active = True

    update_item_barcode_fields(
        bc,
        item_uom_id=next_item_uom_id,
        barcode=next_barcode,
        symbology=next_symbology,
        active=next_active,
        is_primary=body.is_primary,
    )

    db.commit()
    refresh_item_barcode(db, bc)
    return bc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_barcode(id: int, db: Session = Depends(get_db)):
    bc = get_item_barcode_by_id(db, int(id))
    if not bc:
        raise HTTPException(404, "Barcode not found")

    delete_item_barcode(db, bc)
    db.commit()
    return None
