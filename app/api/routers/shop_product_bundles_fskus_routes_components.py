# app/api/routers/shop_product_bundles_fskus_routes_components.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.schemas.fsku import FskuComponentsReplaceIn, FskuDetailOut
from app.db.deps import get_db
from app.services.fsku_service import FskuService

from .shop_product_bundles_fskus_routes_base import _check_write_perm, _svc


def register(r: APIRouter) -> None:
    @r.get("/{fsku_id}/components", response_model=FskuDetailOut)
    def components(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        out = svc.get_detail(fsku_id)
        if out is None:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="FSKU 不存在",
                    context={"fsku_id": fsku_id},
                ),
            )
        return out

    @r.post("/{fsku_id}/components", response_model=FskuDetailOut)
    def replace_components(
        fsku_id: int,
        payload: FskuComponentsReplaceIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        try:
            return svc.replace_components_draft(fsku_id=fsku_id, components=payload.components)
        except FskuService.NotFound as e:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message=str(e),
                    context={"fsku_id": fsku_id},
                ),
            )
        except FskuService.Conflict as e:
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="state_conflict",
                    message=str(e),
                    context={"fsku_id": fsku_id},
                ),
            )
        except FskuService.BadInput as e:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="请求参数不合法",
                    context={"fsku_id": fsku_id},
                    details=e.details,
                ),
            )
