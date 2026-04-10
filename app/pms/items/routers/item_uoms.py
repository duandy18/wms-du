# app/pms/items/routers/item_uoms.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.item_barcode import ItemBarcode
from app.models.item_uom import ItemUOM
from app.pms.items.contracts.item_uom import (
    ItemUomBarcodeRowOut,
    ItemUomCreate,
    ItemUomOut,
    ItemUomUpdate,
)
from app.pms.items.repos.item_uom_repo import (
    create_item_uom,
    delete_item_uom,
    find_other_base_item_uom,
    get_item_uom_by_id,
    has_barcode_refs_for_item_uom,
    has_po_line_refs_for_item_uom,
    has_receipt_line_refs_for_item_uom,
    list_item_uom_row_sources_by_item_ids,
    list_item_uoms_by_item_id,
    list_item_uoms_by_item_ids,
    refresh_item_uom,
    update_item_uom_fields,
)

router = APIRouter(prefix="/item-uoms", tags=["item-uoms"])


def _get_item_uom_or_404(db: Session, item_uom_id: int) -> ItemUOM:
    obj = get_item_uom_by_id(db, int(item_uom_id))
    if not obj:
        raise HTTPException(status_code=404, detail="ItemUom not found")
    return obj


def _barcode_rank(barcode: ItemBarcode) -> tuple[int, str, int]:
    raw_ts = barcode.updated_at or barcode.created_at
    ts = raw_ts.isoformat() if isinstance(raw_ts, datetime) else ""
    return (
        1 if bool(barcode.is_primary) else 0,
        ts,
        int(barcode.id),
    )


def _build_item_uom_barcode_row(
    *,
    item,
    uom: ItemUOM,
    barcode: ItemBarcode | None,
) -> ItemUomBarcodeRowOut:
    row_updated_at = (
        barcode.updated_at
        if barcode is not None and barcode.updated_at is not None
        else barcode.created_at
        if barcode is not None and barcode.created_at is not None
        else uom.updated_at
    )

    return ItemUomBarcodeRowOut(
        sku=str(item.sku),
        item_name=str(item.name),
        item_id=int(item.id),
        item_uom_id=int(uom.id),
        uom=str(uom.uom),
        display_name=str(uom.display_name).strip() if uom.display_name is not None else None,
        ratio_to_base=int(uom.ratio_to_base),
        net_weight_kg=float(uom.net_weight_kg) if uom.net_weight_kg is not None else None,
        is_base=bool(uom.is_base),
        is_purchase_default=bool(uom.is_purchase_default),
        is_inbound_default=bool(uom.is_inbound_default),
        is_outbound_default=bool(uom.is_outbound_default),
        barcode_id=int(barcode.id) if barcode is not None else None,
        barcode=str(barcode.barcode) if barcode is not None else None,
        symbology=str(barcode.symbology) if barcode is not None else None,
        is_primary=bool(barcode.is_primary) if barcode is not None else False,
        active=bool(barcode.active) if barcode is not None else False,
        updated_at=row_updated_at,
    )


@router.post("", response_model=ItemUomOut)
def create_item_uom_route(
    payload: ItemUomCreate,
    db: Session = Depends(get_db),
):
    obj = create_item_uom(
        db,
        item_id=int(payload.item_id),
        uom=str(payload.uom),
        ratio_to_base=int(payload.ratio_to_base),
        display_name=payload.display_name,
        net_weight_kg=payload.net_weight_kg,
        is_base=bool(payload.is_base),
        is_purchase_default=bool(payload.is_purchase_default),
        is_inbound_default=bool(payload.is_inbound_default),
        is_outbound_default=bool(payload.is_outbound_default),
    )
    db.commit()
    refresh_item_uom(db, obj)
    return obj


@router.get("/item/{item_id}", response_model=list[ItemUomOut])
def list_item_uoms(
    item_id: int,
    db: Session = Depends(get_db),
):
    return list_item_uoms_by_item_id(db, int(item_id))


@router.get("/item/{item_id}/rows", response_model=list[ItemUomBarcodeRowOut])
def list_item_uom_rows_for_item(
    item_id: int,
    active_only: bool = Query(False, description="true 时仅挂 active=true 的条码；无条码包装仍返回"),
    db: Session = Depends(get_db),
):
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="invalid item_id")

    rows = list_item_uom_row_sources_by_item_ids(
        db,
        item_ids=[int(item_id)],
        active_only=bool(active_only),
    )
    return [
        _build_item_uom_barcode_row(item=item, uom=uom, barcode=barcode)
        for uom, item, barcode in rows
    ]


@router.get("/by-items", response_model=list[ItemUomOut])
def list_item_uoms_for_items(
    item_id: list[int] = Query(default=[]),
    db: Session = Depends(get_db),
):
    return list_item_uoms_by_item_ids(db, item_id)


@router.get("/rows/by-items", response_model=list[ItemUomBarcodeRowOut])
def list_item_uom_rows_for_items(
    item_id: list[int] = Query(default=[]),
    active_only: bool = Query(False, description="true 时仅挂 active=true 的条码；无条码包装仍返回"),
    db: Session = Depends(get_db),
):
    rows = list_item_uom_row_sources_by_item_ids(
        db,
        item_ids=item_id,
        active_only=bool(active_only),
    )
    return [
        _build_item_uom_barcode_row(item=item, uom=uom, barcode=barcode)
        for uom, item, barcode in rows
    ]


@router.patch("/{id}", response_model=ItemUomOut)
def update_item_uom_route(
    id: int,
    payload: ItemUomUpdate,
    db: Session = Depends(get_db),
):
    obj = get_item_uom_by_id(db, int(id))
    if not obj:
        raise HTTPException(status_code=404, detail="ItemUom not found")

    update_item_uom_fields(
        obj,
        **payload.model_dump(exclude_unset=True),
    )

    db.commit()
    refresh_item_uom(db, obj)
    return obj


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_item_uom_route(
    id: int,
    db: Session = Depends(get_db),
):
    obj = _get_item_uom_or_404(db, int(id))

    if bool(obj.is_base):
        raise HTTPException(
            status_code=400,
            detail="基础包装不能删除",
        )

    if has_barcode_refs_for_item_uom(
        db,
        item_id=int(obj.item_id),
        item_uom_id=int(obj.id),
    ):
        raise HTTPException(
            status_code=409,
            detail="当前包装已绑定条码，不能删除；请先修改条码绑定",
        )

    if has_po_line_refs_for_item_uom(db, item_uom_id=int(obj.id)):
        raise HTTPException(
            status_code=409,
            detail="当前包装已被采购单引用，不能删除",
        )

    if has_receipt_line_refs_for_item_uom(db, item_uom_id=int(obj.id)):
        raise HTTPException(
            status_code=409,
            detail="当前包装已被收货记录引用，不能删除",
        )

    need_fallback_default = bool(
        obj.is_purchase_default or obj.is_inbound_default or obj.is_outbound_default
    )

    if need_fallback_default:
        base = find_other_base_item_uom(
            db,
            item_id=int(obj.item_id),
            exclude_id=int(obj.id),
        )
        if base is None:
            raise HTTPException(
                status_code=409,
                detail="缺少基础包装，无法安全删除当前包装",
            )

        if obj.is_purchase_default:
            base.is_purchase_default = True
        if obj.is_inbound_default:
            base.is_inbound_default = True
        if obj.is_outbound_default:
            base.is_outbound_default = True

    delete_item_uom(db, obj)
    db.commit()
    return {"ok": True}
