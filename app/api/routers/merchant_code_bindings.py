# app/api/routers/merchant_code_bindings.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.services.platform_order_resolve_service import norm_platform, norm_shop_id
from app.services.merchant_code_binding_service import MerchantCodeBindingService
from app.api.routers.merchant_code_bindings_schemas import (
    MerchantCodeBindingBindIn,
    MerchantCodeBindingOut,
    to_out_row,
)

router = APIRouter(tags=["platform-orders"])


@router.post(
    "/merchant-code-bindings/bind",
    response_model=MerchantCodeBindingOut,
    summary="人工绑定：platform+shop_id+merchant_code(current) → published FSKU",
)
async def bind_merchant_code(
    payload: MerchantCodeBindingBindIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> MerchantCodeBindingOut:
    plat = norm_platform(payload.platform)
    shop_id = norm_shop_id(payload.shop_id)

    svc = MerchantCodeBindingService(session)
    try:
        obj = await svc.bind_current(
            platform=plat,
            shop_id=int(shop_id),
            merchant_code=payload.merchant_code,
            fsku_id=int(payload.fsku_id),
            reason=payload.reason,
        )
        await session.commit()
        await session.refresh(obj)
        return MerchantCodeBindingOut(
            ok=True,
            data=to_out_row(
                id=obj.id,
                platform=obj.platform,
                shop_id=obj.shop_id,
                merchant_code=obj.merchant_code,
                fsku_id=obj.fsku_id,
                effective_from=obj.effective_from,
                effective_to=obj.effective_to,
                reason=obj.reason,
                created_at=obj.created_at,
            ),
        )
    except MerchantCodeBindingService.BadInput as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=e.message,
                context={"platform": plat, "shop_id": shop_id},
            ),
        )
    except MerchantCodeBindingService.NotFound as e:
        raise HTTPException(
            status_code=404,
            detail=make_problem(
                status_code=404,
                error_code="not_found",
                message=str(e),
                context={"platform": plat, "shop_id": shop_id},
            ),
        )
    except MerchantCodeBindingService.Conflict as e:
        raise HTTPException(
            status_code=409,
            detail=make_problem(
                status_code=409,
                error_code="conflict",
                message=str(e),
                context={"platform": plat, "shop_id": shop_id},
            ),
        )
    except Exception as e:
        # 并发/unique 冲突等兜底（让问题可见）
        raise HTTPException(
            status_code=409,
            detail=make_problem(
                status_code=409,
                error_code="conflict",
                message=f"绑定写入失败：{str(e)}",
                context={"platform": plat, "shop_id": shop_id},
            ),
        )
