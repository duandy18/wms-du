from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SchemeCreateIn,
    SchemeDetailOut,
)
from app.api.routers.shipping_provider_pricing_schemes.validators import (
    validate_default_pricing_mode,
)
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_nonempty,
    validate_effective_window,
)
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def register_create_routes(router: APIRouter) -> None:
    @router.post(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeDetailOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_scheme(
        provider_id: int = Path(..., ge=1),
        payload: SchemeCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        provider = db.get(ShippingProvider, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        if getattr(payload, "warehouse_id", None) is None:
            raise HTTPException(status_code=422, detail="warehouse_id is required")
        warehouse_id = int(getattr(payload, "warehouse_id"))
        if warehouse_id <= 0:
            raise HTTPException(status_code=422, detail="warehouse_id must be >= 1")

        wh_ok = db.execute(
            text("SELECT 1 FROM warehouses WHERE id = :wid LIMIT 1"),
            {"wid": warehouse_id},
        ).first()
        if not wh_ok:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        wsp_ok = db.execute(
            text(
                """
                SELECT 1
                  FROM warehouse_shipping_providers
                 WHERE warehouse_id = :wid
                   AND shipping_provider_id = :pid
                   AND active = true
                 LIMIT 1
                """
            ),
            {"wid": warehouse_id, "pid": int(provider_id)},
        ).first()
        if not wsp_ok:
            raise HTTPException(status_code=409, detail="ShippingProvider not enabled for this warehouse")

        validate_effective_window(payload.effective_from, payload.effective_to)

        try:
            dpm = validate_default_pricing_mode(payload.default_pricing_mode)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        next_active = bool(payload.active)

        if next_active:
            (
                db.query(ShippingProviderPricingScheme.id)
                .filter(
                    ShippingProviderPricingScheme.shipping_provider_id == int(provider_id),
                    ShippingProviderPricingScheme.warehouse_id == int(warehouse_id),
                )
                .with_for_update()
                .all()
            )

            db.execute(
                update(ShippingProviderPricingScheme)
                .where(
                    ShippingProviderPricingScheme.shipping_provider_id == int(provider_id),
                    ShippingProviderPricingScheme.warehouse_id == int(warehouse_id),
                    ShippingProviderPricingScheme.archived_at.is_(None),
                    ShippingProviderPricingScheme.active.is_(True),
                )
                .values(active=False)
            )

        sch = ShippingProviderPricingScheme(
            warehouse_id=int(warehouse_id),
            shipping_provider_id=int(provider_id),
            name=norm_nonempty(payload.name, "name"),
            active=next_active,
            currency=(payload.currency or "CNY").strip() or "CNY",
            default_pricing_mode=dpm,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            billable_weight_rule=payload.billable_weight_rule,
        )
        db.add(sch)
        db.commit()
        db.refresh(sch)

        return SchemeDetailOut(ok=True, data=to_scheme_out(sch, destination_groups=[], surcharges=[]))
