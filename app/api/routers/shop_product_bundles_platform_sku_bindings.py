# app/api/routers/shop_product_bundles_platform_sku_bindings.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.problem import make_problem
from app.api.schemas.platform_sku_binding import (
    BindingCreateIn,
    BindingCurrentOut,
    BindingHistoryOut,
    BindingMigrateIn,
    BindingMigrateOut,
    BindingUnbindIn,
)
from app.db.deps import get_db
from app.services.platform_sku_binding_service import PlatformSkuBindingService


def _svc(db: Session = Depends(get_db)) -> PlatformSkuBindingService:
    return PlatformSkuBindingService(db)


def _pick_store_id(*, store_id: int | None, shop_id: int | None) -> int:
    """
    ✅ 合同升级（兼容期）：
    - 新参数：store_id（内部 stores.id）
    - 旧参数：shop_id（兼容旧字段名，语义等同 stores.id）
    """
    if store_id is not None:
        return int(store_id)
    if shop_id is not None:
        return int(shop_id)
    raise ValueError("store_id is required")


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/platform-sku-bindings", tags=["ops - shop-product-bundles"])

    @r.get("/current", response_model=BindingCurrentOut)
    def current(
        platform: str = Query(...),
        store_id: int | None = Query(None, ge=1, description="内部店铺ID（stores.id）"),
        shop_id: int | None = Query(None, ge=1, description="兼容旧参数：语义等同 stores.id"),
        platform_sku_id: str = Query(...),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingCurrentOut:
        # 权限：治理类写权限
        svc.db  # satisfy type checkers
        from app.api.routers.stores_helpers import check_perm  # 局部导入避免循环依赖风险

        check_perm(svc.db, current_user, ["config.store.write"])
        try:
            sid = _pick_store_id(store_id=store_id, shop_id=shop_id)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 不能为空",
                    context={"platform": platform, "platform_sku_id": platform_sku_id},
                ),
            )
        out = svc.get_current(platform=platform, store_id=sid, platform_sku_id=platform_sku_id)
        if out is None:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message="未找到当前绑定",
                    context={"platform": platform, "store_id": sid, "platform_sku_id": platform_sku_id},
                ),
            )
        return out

    @r.get("/history", response_model=BindingHistoryOut)
    def history(
        platform: str = Query(...),
        store_id: int | None = Query(None, ge=1, description="内部店铺ID（stores.id）"),
        shop_id: int | None = Query(None, ge=1, description="兼容旧参数：语义等同 stores.id"),
        platform_sku_id: str = Query(...),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingHistoryOut:
        from app.api.routers.stores_helpers import check_perm  # 局部导入避免循环依赖风险

        check_perm(svc.db, current_user, ["config.store.write"])
        try:
            sid = _pick_store_id(store_id=store_id, shop_id=shop_id)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 不能为空",
                    context={"platform": platform, "platform_sku_id": platform_sku_id},
                ),
            )
        return svc.get_history(
            platform=platform,
            store_id=sid,
            platform_sku_id=platform_sku_id,
            limit=limit,
            offset=offset,
        )

    @r.post("", response_model=BindingCurrentOut, status_code=status.HTTP_201_CREATED)
    def bind(
        payload: BindingCreateIn,
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingCurrentOut:
        from app.api.routers.stores_helpers import check_perm  # 局部导入避免循环依赖风险

        check_perm(svc.db, current_user, ["config.store.write"])
        try:
            sid = _pick_store_id(store_id=payload.store_id, shop_id=payload.shop_id)
            return svc.bind(
                platform=payload.platform,
                store_id=sid,
                platform_sku_id=payload.platform_sku_id,
                fsku_id=payload.fsku_id,
                reason=payload.reason,
            )
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 不能为空",
                    context={"platform": payload.platform, "platform_sku_id": payload.platform_sku_id},
                ),
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

    @r.post("/unbind", status_code=status.HTTP_204_NO_CONTENT)
    def unbind(
        payload: BindingUnbindIn,
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> None:
        from app.api.routers.stores_helpers import check_perm  # 局部导入避免循环依赖风险

        check_perm(svc.db, current_user, ["config.store.write"])
        try:
            sid = _pick_store_id(store_id=payload.store_id, shop_id=payload.shop_id)
            svc.unbind(
                platform=payload.platform,
                store_id=sid,
                platform_sku_id=payload.platform_sku_id,
                reason=payload.reason,
            )
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=make_problem(
                    status_code=422,
                    error_code="request_validation_error",
                    message="store_id 不能为空",
                    context={"platform": payload.platform, "platform_sku_id": payload.platform_sku_id},
                ),
            )
        except PlatformSkuBindingService.NotFound as e:
            raise HTTPException(
                status_code=404,
                detail=make_problem(
                    status_code=404,
                    error_code="not_found",
                    message=str(e),
                    context={
                        "platform": payload.platform,
                        "store_id": sid,
                        "platform_sku_id": payload.platform_sku_id,
                    },
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
        current_user=Depends(get_current_user),
        svc: PlatformSkuBindingService = Depends(_svc),
    ) -> BindingMigrateOut:
        from app.api.routers.stores_helpers import check_perm  # 局部导入避免循环依赖风险

        check_perm(svc.db, current_user, ["config.store.write"])
        try:
            return svc.migrate(
                binding_id=binding_id,
                to_fsku_id=payload.to_fsku_id,
                reason=payload.reason,
            )
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
