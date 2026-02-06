# app/api/routers/shop_product_bundles_fskus.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.fsku import (
    FskuComponentsReplaceIn,
    FskuCreateIn,
    FskuDetailOut,
    FskuListOut,
    FskuNameUpdateIn,
)
from app.db.deps import get_db
from app.services.fsku_service import FskuService


def _svc(db: Session = Depends(get_db)) -> FskuService:
    return FskuService(db)


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/fskus", tags=["ops - shop-product-bundles"])

    @r.post("", response_model=FskuDetailOut, status_code=status.HTTP_201_CREATED)
    def create(
        payload: FskuCreateIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        check_perm(db, current_user, ["config.store.write"])
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
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuListOut:
        check_perm(db, current_user, ["config.store.write"])
        return svc.list_fskus(query=query, status=status_, limit=limit, offset=offset)

    @r.get("/{fsku_id}", response_model=FskuDetailOut)
    def detail(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        check_perm(db, current_user, ["config.store.write"])
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
        check_perm(db, current_user, ["config.store.write"])
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

    @r.get("/{fsku_id}/components", response_model=FskuDetailOut)
    def components(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        check_perm(db, current_user, ["config.store.write"])
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
        check_perm(db, current_user, ["config.store.write"])
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

    @r.post("/{fsku_id}/publish", response_model=FskuDetailOut)
    def publish(
        fsku_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: FskuService = Depends(_svc),
    ) -> FskuDetailOut:
        check_perm(db, current_user, ["config.store.write"])
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
        check_perm(db, current_user, ["config.store.write"])
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
        ✅ 取消归档（恢复）
        - 仅允许 status=retired 的 FSKU 取消归档
        - 取消后 status=published；retired_at 清空；published_at 保持历史值
        """
        check_perm(db, current_user, ["config.store.write"])
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

    router.include_router(r)
