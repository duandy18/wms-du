# app/api/routers/shop_product_bundles_platform_sku_bindings.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.routers.stores_helpers import check_perm
from app.api.schemas.platform_sku_binding import (
    BindingCreateIn,
    BindingCurrentOut,
    BindingHistoryOut,
    BindingMigrateIn,
    BindingMigrateOut,
)
from app.db.deps import get_db
from app.services.platform_sku_binding_service import PlatformSkuBindingService


def _svc(db: Session = Depends(get_db)) -> PlatformSkuBindingService:
    return PlatformSkuBindingService(db)


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/platform-sku-bindings", tags=["ops - shop-product-bundles"])

    @r.get("/current", response_model=BindingCurrentOut)
    def current(
        platform: str = Query(...),
        shop_id: int = Query(..., ge=1),
        platform_sku_id: str = Query(...),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingCurrentOut:
        check_perm(db, current_user, ["config.store.write"])
        out = svc.get_current(platform=platform, shop_id=shop_id, platform_sku_id=platform_sku_id)
        if out is None:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="未找到当前绑定",
                    context={"platform": platform, "shop_id": shop_id, "platform_sku_id": platform_sku_id},
                ),
            )
        return out

    @r.get("/history", response_model=BindingHistoryOut)
    def history(
        platform: str = Query(...),
        shop_id: int = Query(..., ge=1),
        platform_sku_id: str = Query(...),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingHistoryOut:
        check_perm(db, current_user, ["config.store.write"])
        return svc.get_history(
            platform=platform,
            shop_id=shop_id,
            platform_sku_id=platform_sku_id,
            limit=limit,
            offset=offset,
        )

    @r.post("", response_model=BindingCurrentOut, status_code=status.HTTP_201_CREATED)
    def bind(
        payload: BindingCreateIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingCurrentOut:
        check_perm(db, current_user, ["config.store.write"])
        try:
            return svc.bind(
                platform=payload.platform,
                shop_id=payload.shop_id,
                platform_sku_id=payload.platform_sku_id,
                fsku_id=payload.fsku_id,
                reason=payload.reason,
            )
        except PlatformSkuBindingService.NotFound as e:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message=str(e),
                ),
            )
        except PlatformSkuBindingService.Conflict as e:
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="state_conflict",
                    message=str(e),
                ),
            )

    @r.post("/{binding_id}/migrate", response_model=BindingMigrateOut)
    def migrate(
        binding_id: int,
        payload: BindingMigrateIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingMigrateOut:
        check_perm(db, current_user, ["config.store.write"])
        try:
            return svc.migrate(binding_id=binding_id, to_fsku_id=payload.to_fsku_id, reason=payload.reason)
        except PlatformSkuBindingService.NotFound as e:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message=str(e),
                    context={"binding_id": binding_id},
                ),
            )
        except PlatformSkuBindingService.Conflict as e:
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="state_conflict",
                    message=str(e),
                    context={"binding_id": binding_id},
                ),
            )

    router.include_router(r)
