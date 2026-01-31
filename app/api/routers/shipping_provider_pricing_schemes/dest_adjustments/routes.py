# app/api/routers/shipping_provider_pricing_schemes/dest_adjustments/routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.services.pricing_scheme_dest_adjustment_service import (
    delete_dest_adjustment,
    upsert_dest_adjustment,
    update_dest_adjustment,
)

from app.api.routers.shipping_provider_pricing_schemes.schemas.dest_adjustment import (
    DestAdjustmentOut,
    DestAdjustmentUpdateIn,
    DestAdjustmentUpsertIn,
)


def _to_out(x: PricingSchemeDestAdjustment) -> DestAdjustmentOut:
    return DestAdjustmentOut(
        id=int(x.id),
        scheme_id=int(x.scheme_id),
        scope=str(x.scope),
        province_code=str(x.province_code),
        city_code=str(x.city_code) if x.city_code is not None else None,
        province_name=str(x.province_name) if x.province_name is not None else None,
        city_name=str(x.city_name) if x.city_name is not None else None,
        province=str(x.province),
        city=str(x.city) if x.city is not None else None,
        amount=float(x.amount),
        active=bool(x.active),
        priority=int(x.priority or 100),
        created_at=x.created_at,
        updated_at=x.updated_at,
    )


def register_dest_adjustments_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/dest-adjustments",
        response_model=list[DestAdjustmentOut],
    )
    def list_dest_adjustments(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        rows = (
            db.query(PricingSchemeDestAdjustment)
            .filter(PricingSchemeDestAdjustment.scheme_id == int(scheme_id))
            .order_by(PricingSchemeDestAdjustment.id.asc())
            .all()
        )
        return [_to_out(x) for x in rows]

    @router.post(
        "/pricing-schemes/{scheme_id}/dest-adjustments:upsert",
        response_model=DestAdjustmentOut,
        status_code=status.HTTP_200_OK,
    )
    def upsert_dest_adjustments(
        scheme_id: int = Path(..., ge=1),
        payload: DestAdjustmentUpsertIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        ✅ 新主入口（事实写入点，严格 code 世界）：
        - 输入：scope + province_code(+city_code) + amount + active + priority
        - 行为：同 key 则更新，否则创建（幂等）
        - 互斥：同省 province vs city active 互斥（service 层硬约束）
        """
        check_perm(db, user, "config.store.write")

        row = upsert_dest_adjustment(
            db,
            scheme_id=int(scheme_id),
            scope=payload.scope,
            province_code=payload.province_code,
            city_code=payload.city_code,
            province_name=payload.province_name,
            city_name=payload.city_name,
            amount=payload.amount,
            active=bool(payload.active),
            priority=int(payload.priority),
        )
        return _to_out(row)

    @router.patch(
        "/dest-adjustments/{dest_adjustment_id}",
        response_model=DestAdjustmentOut,
    )
    def patch_dest_adjustment(
        dest_adjustment_id: int = Path(..., ge=1),
        payload: DestAdjustmentUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        data = payload.model_dump(exclude_unset=True)

        row = update_dest_adjustment(
            db,
            dest_adjustment_id=int(dest_adjustment_id),
            scope=data.get("scope"),
            province_code=data.get("province_code"),
            city_code=data.get("city_code"),
            province_name=data.get("province_name"),
            city_name=data.get("city_name"),
            amount=data.get("amount"),
            active=data.get("active"),
            priority=data.get("priority"),
        )
        return _to_out(row)

    @router.delete(
        "/dest-adjustments/{dest_adjustment_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_dest_adjustment_route(
        dest_adjustment_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        delete_dest_adjustment(db, dest_adjustment_id=int(dest_adjustment_id))
        return {"ok": True}
