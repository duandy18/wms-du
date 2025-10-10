# app/api/endpoints/stock.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stock import StockAdjustIn, StockAdjustOut, StockQueryOut, StockRow, StockSummary
from app.services.stock_service import StockService

router = APIRouter(prefix="/stock", tags=["stock"])


@router.post("/adjust", response_model=StockAdjustOut)
def adjust_stock(payload: StockAdjustIn, db: Session = Depends(get_db)):
    svc = StockService(db)
    try:
        item_id, before_qty, delta, new_qty = svc.adjust_sync(
            item_id=payload.item_id,
            location_id=payload.location_id,
            delta=payload.delta,
            reason=payload.reason,
            ref=payload.ref,
            allow_negative=payload.allow_negative,
        )
    except ValueError as e:
        # 测试期望负库存保护 → 409
        raise HTTPException(status_code=409, detail=str(e))
    return StockAdjustOut(
        item_id=item_id,
        location_id=payload.location_id,
        before_quantity=before_qty,
        delta=delta,
        new_quantity=new_qty,
    )


@router.get("/query", response_model=StockQueryOut)
def query_stock(
    item_id: int | None = None,
    warehouse_id: int | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db),
):
    svc = StockService(db)
    rows = [
        StockRow(
            item_id=r.item_id,
            location_id=r.location_id,
            quantity=r.quantity,
            warehouse_id=(
                getattr(r, "location", None).warehouse_id if getattr(r, "location", None) else None
            ),
        )
        for r in svc.query_rows(item_id=item_id, warehouse_id=warehouse_id, location_id=location_id)
    ]
    on_hand = sum(float(r.quantity or 0) for r in rows)
    summary = [StockSummary(item_id=(item_id or 0), on_hand=on_hand)]
    return StockQueryOut(rows=rows, summary=summary)
