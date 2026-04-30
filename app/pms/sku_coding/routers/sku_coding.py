# app/pms/sku_coding/routers/sku_coding.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.sku_coding.contracts.sku_coding import (
    SkuGenerateIn,
    SkuGenerateOut,
)
from app.pms.sku_coding.services.sku_coding_service import SkuCodingService

router = APIRouter(prefix="/pms/sku-coding", tags=["pms-sku-coding"])


@router.post("/generate", response_model=SkuGenerateOut)
def generate_sku(payload: SkuGenerateIn, db: Session = Depends(get_db)):
    try:
        data = SkuCodingService(db).generate(
            product_kind=payload.product_kind,
            brand_id=int(payload.brand_id),
            category_id=int(payload.category_id),
            attribute_option_ids=payload.attribute_option_ids,
            text_segments=payload.text_segments,
            spec_text=payload.spec_text,
        )
        return {"ok": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
