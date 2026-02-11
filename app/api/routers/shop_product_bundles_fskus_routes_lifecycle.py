# app/api/routers/shop_product_bundles_fskus_routes_lifecycle.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.schemas.fsku import FskuDetailOut
from app.db.deps import get_db
from app.services.fsku_service import FskuService

from .shop_product_bundles_fskus_routes_base import _check_write_perm, _svc


def register(r: APIRouter) -> None:
    @r.post("/{fsku_id}/publish", response_model=FskuDetailOut)
    def publish(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        try:
            return svc.publish(fsku_id)
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

    @r.post("/{fsku_id}/retire", response_model=FskuDetailOut)
    def retire(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        try:
            return svc.retire(fsku_id)
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

    @r.post("/{fsku_id}/unretire", response_model=FskuDetailOut)
    def unretire(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        """
        ⚠️ 兼容保留：取消归档（不支持）
        - 系统封板：FSKU 生命周期单向（draft → published → retired）
        - 发布事实不可逆，因此该接口将始终返回 409（state_conflict）
        """
        _check_write_perm(db, current_user)
        try:
            return svc.unretire(fsku_id)
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
