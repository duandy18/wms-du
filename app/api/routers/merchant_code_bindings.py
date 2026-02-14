# app/api/routers/merchant_code_bindings.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem
from app.api.routers.merchant_code_bindings_schemas import (
    FskuLiteOut,
    MerchantCodeBindingBindIn,
    MerchantCodeBindingCloseIn,
    MerchantCodeBindingListDataOut,
    MerchantCodeBindingListOut,
    MerchantCodeBindingOut,
    MerchantCodeBindingRowOut,
    StoreLiteOut,
)
from app.models.fsku import Fsku
from app.models.merchant_code_fsku_binding import MerchantCodeFskuBinding
from app.models.store import Store
from app.services.merchant_code_binding_service import MerchantCodeBindingService
from app.services.platform_order_resolve_service import norm_platform, norm_shop_id
from app.services.test_shop_testset_guard_service import TestShopTestSetGuardService

router = APIRouter(tags=["merchant-code-bindings"])


def _row_out(*, b: MerchantCodeFskuBinding, f: Fsku, store: Store) -> MerchantCodeBindingRowOut:
    return MerchantCodeBindingRowOut(
        id=int(b.id),
        platform=b.platform,
        shop_id=str(b.shop_id),
        store=StoreLiteOut(id=int(store.id), name=str(store.name)),
        merchant_code=b.merchant_code,
        fsku_id=int(b.fsku_id),
        fsku=FskuLiteOut(id=int(f.id), code=f.code, name=f.name, status=str(f.status)),
        reason=b.reason,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


@router.get(
    "/merchant-code-bindings",
    response_model=MerchantCodeBindingListOut,
    summary="列表：merchant_code ↔ published FSKU 绑定（一码一对一，分页 + 过滤）",
)
async def list_merchant_code_bindings(
    platform: str | None = Query(None, min_length=1, max_length=32),
    shop_id: str | None = Query(None, min_length=1, max_length=64),
    merchant_code: str | None = Query(None, min_length=1, max_length=128),
    # ✅ 兼容字段：简化模型下无历史，无 effective_to；该参数忽略
    current_only: bool = Query(True),
    fsku_id: int | None = Query(None, ge=1),
    fsku_code: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> MerchantCodeBindingListOut:
    try:
        plat = norm_platform(platform) if platform else None
        sid = norm_shop_id(shop_id) if shop_id else None
        mc = (merchant_code or "").strip() or None
        fc = (fsku_code or "").strip() or None

        conds = []
        if plat is not None:
            conds.append(MerchantCodeFskuBinding.platform == plat)
        if sid is not None:
            conds.append(MerchantCodeFskuBinding.shop_id == sid)
        if mc is not None:
            conds.append(MerchantCodeFskuBinding.merchant_code.like(f"%{mc}%"))
        if fsku_id is not None:
            conds.append(MerchantCodeFskuBinding.fsku_id == int(fsku_id))
        if fc is not None:
            conds.append(Fsku.code.like(f"%{fc}%"))

        total_stmt = (
            select(func.count())
            .select_from(MerchantCodeFskuBinding)
            .join(Fsku, Fsku.id == MerchantCodeFskuBinding.fsku_id)
            .join(Store, (Store.platform == MerchantCodeFskuBinding.platform) & (Store.shop_id == MerchantCodeFskuBinding.shop_id))
        )
        if conds:
            total_stmt = total_stmt.where(*conds)

        total = int((await session.execute(total_stmt)).scalar_one())

        stmt = (
            select(MerchantCodeFskuBinding, Fsku, Store)
            .join(Fsku, Fsku.id == MerchantCodeFskuBinding.fsku_id)
            .join(Store, (Store.platform == MerchantCodeFskuBinding.platform) & (Store.shop_id == MerchantCodeFskuBinding.shop_id))
            .order_by(MerchantCodeFskuBinding.id.desc())
            .limit(int(limit))
            .offset(int(offset))
        )
        if conds:
            stmt = stmt.where(*conds)

        rows = (await session.execute(stmt)).all()
        items: list[MerchantCodeBindingRowOut] = [_row_out(b=r[0], f=r[1], store=r[2]) for r in rows]

        return MerchantCodeBindingListOut(
            ok=True,
            data=MerchantCodeBindingListDataOut(items=items, total=total, limit=int(limit), offset=int(offset)),
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=f"查询参数不合法：{str(e)}",
                context={"platform": platform, "shop_id": shop_id, "limit": int(limit), "offset": int(offset)},
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=make_problem(
                status_code=500,
                error_code="internal_error",
                message=f"读取绑定列表失败：{str(e)}",
                context={"platform": platform, "shop_id": shop_id, "limit": int(limit), "offset": int(offset)},
            ),
        )


@router.post(
    "/merchant-code-bindings/bind",
    response_model=MerchantCodeBindingOut,
    summary="人工绑定/覆盖：platform+shop_id+merchant_code → published FSKU（一码一对一）",
)
async def bind_merchant_code(
    payload: MerchantCodeBindingBindIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> MerchantCodeBindingOut:
    plat = norm_platform(payload.platform)
    shop_id = norm_shop_id(payload.shop_id)

    # ✅ 宇宙边界（以 platform_test_shops 为唯一真相）：
    #    - 有 components 才校验；无 components 直接放行（合同兼容）
    guard = TestShopTestSetGuardService(session)
    await guard.guard_fsku_components_by_shop(
        platform=plat,
        shop_id=shop_id,
        store_id=None,
        fsku_id=int(payload.fsku_id),
        set_code="DEFAULT",
        path="/merchant-code-bindings/bind",
        method="POST",
    )

    svc = MerchantCodeBindingService(session)
    try:
        obj = await svc.bind_upsert(
            platform=plat,
            shop_id=shop_id,
            merchant_code=payload.merchant_code,
            fsku_id=int(payload.fsku_id),
            reason=payload.reason,
        )
        await session.commit()
        await session.refresh(obj)

        f = await session.get(Fsku, int(obj.fsku_id))
        if f is None:
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message="绑定已写入但 FSKU 不存在（FK 断裂）",
                    context={"platform": plat, "shop_id": shop_id, "merchant_code": obj.merchant_code, "fsku_id": int(obj.fsku_id)},
                ),
            )

        store = (
            await session.execute(select(Store).where(Store.platform == plat, Store.shop_id == shop_id).limit(1))
        ).scalars().first()
        if store is None:
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message="绑定已写入但 Store 不存在（platform+shop_id 未建档）",
                    context={"platform": plat, "shop_id": shop_id},
                ),
            )

        return MerchantCodeBindingOut(ok=True, data=_row_out(b=obj, f=f, store=store))

    except MerchantCodeBindingService.BadInput as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(status_code=422, error_code="request_validation_error", message=e.message, context={"platform": plat, "shop_id": shop_id}),
        )
    except MerchantCodeBindingService.NotFound as e:
        raise HTTPException(
            status_code=404,
            detail=make_problem(status_code=404, error_code="not_found", message=str(e), context={"platform": plat, "shop_id": shop_id}),
        )
    except MerchantCodeBindingService.Conflict as e:
        raise HTTPException(
            status_code=409,
            detail=make_problem(status_code=409, error_code="conflict", message=str(e), context={"platform": plat, "shop_id": shop_id}),
        )
    except Exception as e:
        raise HTTPException(
            status_code=409,
            detail=make_problem(status_code=409, error_code="conflict", message=f"绑定写入失败：{str(e)}", context={"platform": plat, "shop_id": shop_id}),
        )


@router.post(
    "/merchant-code-bindings/close",
    response_model=MerchantCodeBindingOut,
    summary="解绑：删除绑定（一码一对一）",
)
async def close_merchant_code_binding(
    payload: MerchantCodeBindingCloseIn = Body(...),
    session: AsyncSession = Depends(get_session),
) -> MerchantCodeBindingOut:
    plat = norm_platform(payload.platform)
    shop_id = norm_shop_id(payload.shop_id)

    svc = MerchantCodeBindingService(session)
    try:
        obj = await svc.unbind(
            platform=plat,
            shop_id=shop_id,
            merchant_code=payload.merchant_code,
        )
        await session.commit()

        f = await session.get(Fsku, int(obj.fsku_id))
        if f is None:
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message="绑定已解绑但 FSKU 不存在（FK 断裂）",
                    context={"platform": plat, "shop_id": shop_id, "merchant_code": payload.merchant_code},
                ),
            )

        store = (
            await session.execute(select(Store).where(Store.platform == plat, Store.shop_id == shop_id).limit(1))
        ).scalars().first()
        if store is None:
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message="绑定已解绑但 Store 不存在（platform+shop_id 未建档）",
                    context={"platform": plat, "shop_id": shop_id},
                ),
            )

        return MerchantCodeBindingOut(ok=True, data=_row_out(b=obj, f=f, store=store))

    except MerchantCodeBindingService.BadInput as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(status_code=422, error_code="request_validation_error", message=e.message, context={"platform": plat, "shop_id": shop_id}),
        )
    except MerchantCodeBindingService.NotFound as e:
        raise HTTPException(
            status_code=404,
            detail=make_problem(status_code=404, error_code="not_found", message=str(e), context={"platform": plat, "shop_id": shop_id}),
        )
    except Exception as e:
        raise HTTPException(
            status_code=409,
            detail=make_problem(status_code=409, error_code="conflict", message=f"解绑失败：{str(e)}", context={"platform": plat, "shop_id": shop_id}),
        )
