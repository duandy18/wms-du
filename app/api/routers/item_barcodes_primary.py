# app/api/routers/item_barcodes_primary.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.item_barcode import ItemBarcode

router = APIRouter(prefix="/item-barcodes", tags=["item-barcodes"])


@router.post("/{barcode_id}/primary", status_code=204)
def set_primary_barcode(
    barcode_id: int,
    db: Session = Depends(get_db),
):
    """将此条码设为主条码（is_primary = true）"""

    # 找条码
    bc = db.get(ItemBarcode, barcode_id)
    if not bc:
        raise HTTPException(status_code=404, detail="Barcode not found")

    item_id = bc.item_id

    # 先全部设为非主条码
    db.execute(update(ItemBarcode).where(ItemBarcode.item_id == item_id).values(is_primary=False))

    # 再设定当前条码为主条码
    db.execute(update(ItemBarcode).where(ItemBarcode.id == barcode_id).values(is_primary=True))

    db.commit()
    return None
