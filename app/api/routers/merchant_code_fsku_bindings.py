# app/api/routers/merchant_code_fsku_bindings.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas.merchant_code_fsku_binding import (
    MerchantCodeBindingCreateIn,
    MerchantCodeBindingOut,
)
from app.db.deps import get_db  # 你们项目里通常有这个；若名字不同，贴出来我再改
from app.services.merchant_code_fsku_binding_service import MerchantCodeFskuBindingService

router = APIRouter(prefix="/merchant-code-bindings", tags=["merchant-code-bindings"])


@router.post("", response_model=MerchantCodeBindingOut)
def create_binding(body: MerchantCodeBindingCreateIn, db: Session = Depends(get_db)) -> MerchantCodeBindingOut:
    svc = MerchantCodeFskuBindingService(db)
    try:
        return svc.bind_current(
            platform=body.platform,
            shop_id=body.shop_id,
            merchant_code=body.merchant_code,
            fsku_id=body.fsku_id,
            reason=body.reason,
        )
    except MerchantCodeFskuBindingService.BadInput as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e.message))
    except MerchantCodeFskuBindingService.NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MerchantCodeFskuBindingService.Conflict as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
