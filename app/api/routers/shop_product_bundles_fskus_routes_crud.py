# app/api/routers/shop_product_bundles_fskus_routes_crud.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.schemas.fsku import FskuCreateIn, FskuDetailOut, FskuListOut, FskuNameUpdateIn
from app.db.deps import get_db
from app.services import fsku_service_read
from app.services.fsku_service import FskuService

from .shop_product_bundles_fskus_routes_base import _check_write_perm, _svc


def register(r: APIRouter) -> None:
    @r.post("", response_model=FskuDetailOut, status_code=status.HTTP_201_CREATED)
    def create(
        payload: FskuCreateIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        try:
            return svc.create_draft(name=payload.name, code=payload.code, shape=payload.shape)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message=str(e),
                    context={},
                    details=[{"type": "validation", "path": "shape", "reason": str(e)}],
                ),
            )
        except FskuService.Conflict as e:
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="state_conflict",
                    message=str(e),
                    context={},
                ),
            )

    @r.get("", response_model=FskuListOut)
    def list_(
        query: str | None = Query(None, description="按 name/code 模糊搜索"),
        status_: str | None = Query(None, alias="status", description="draft/published/retired"),
        store_id: int | None = Query(None, ge=1, description="店铺上下文：PROD 店铺将过滤测试 FSKU；TEST 店铺不过滤"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> FskuListOut:
        _check_write_perm(db, current_user)
        return fsku_service_read.list_fskus(db, query=query, status=status_, store_id=store_id, limit=limit, offset=offset)

    @r.get("/{fsku_id}", response_model=FskuDetailOut)
    def detail(
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

    @r.patch("/{fsku_id}", response_model=FskuDetailOut)
    def patch_fsku(
        fsku_id: int,
        payload: FskuNameUpdateIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        _check_write_perm(db, current_user)
        try:
            return svc.update_name(fsku_id=fsku_id, name=payload.name)
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
