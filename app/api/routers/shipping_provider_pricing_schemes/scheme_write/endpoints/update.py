from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SchemeDetailOut,
    SchemeUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes.validators import (
    validate_default_pricing_mode,
)
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_nonempty,
    validate_effective_window,
)
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def _activate_scheme_exclusive(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    """
    系统级裁决：同一 provider + warehouse 下，任意时刻只能有一个 active=true（且 archived_at is null）。
    """
    sch = (
        db.query(ShippingProviderPricingScheme)
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .with_for_update()
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    if sch.archived_at is not None:
        raise HTTPException(status_code=400, detail="Archived scheme cannot be activated")

    provider_id = int(sch.shipping_provider_id)
    warehouse_id = int(sch.warehouse_id)

    (
        db.query(ShippingProviderPricingScheme.id)
        .filter(
            ShippingProviderPricingScheme.shipping_provider_id == provider_id,
            ShippingProviderPricingScheme.warehouse_id == warehouse_id,
        )
        .with_for_update()
        .all()
    )

    db.execute(
        update(ShippingProviderPricingScheme)
        .where(
            ShippingProviderPricingScheme.shipping_provider_id == provider_id,
            ShippingProviderPricingScheme.warehouse_id == warehouse_id,
            ShippingProviderPricingScheme.id != scheme_id,
            ShippingProviderPricingScheme.archived_at.is_(None),
            ShippingProviderPricingScheme.active.is_(True),
        )
        .values(active=False)
    )

    sch.active = True
    return sch


def register_update_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/activate-exclusive",
        response_model=SchemeDetailOut,
    )
    def activate_scheme_exclusive(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = _activate_scheme_exclusive(db, scheme_id)

        db.commit()
        db.refresh(sch)

        sch2, destination_groups, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(
            ok=True,
            data=to_scheme_out(sch2, destination_groups=destination_groups, surcharges=surcharges),
        )

    @router.patch(
        "/pricing-schemes/{scheme_id}",
        response_model=SchemeDetailOut,
    )
    def update_scheme(
        scheme_id: int = Path(..., ge=1),
        payload: SchemeUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        fields_set = payload.model_fields_set
        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            sch.name = norm_nonempty(data.get("name"), "name")

        if "archived_at" in fields_set:
            sch.archived_at = payload.archived_at
            if sch.archived_at is not None:
                sch.active = False

        if "active" in data:
            next_active = bool(data["active"])
            if next_active:
                if sch.archived_at is not None:
                    raise HTTPException(status_code=400, detail="Archived scheme cannot be activated")
                _activate_scheme_exclusive(db, scheme_id)
            else:
                sch.active = False

        if "currency" in data:
            sch.currency = (data["currency"] or "CNY").strip() or "CNY"

        if "effective_from" in data:
            sch.effective_from = data["effective_from"]
        if "effective_to" in data:
            sch.effective_to = data["effective_to"]

        validate_effective_window(sch.effective_from, sch.effective_to)

        if "billable_weight_rule" in data:
            sch.billable_weight_rule = data["billable_weight_rule"]

        if "default_pricing_mode" in data:
            try:
                sch.default_pricing_mode = validate_default_pricing_mode(data["default_pricing_mode"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        db.commit()
        db.refresh(sch)

        sch2, destination_groups, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(
            ok=True,
            data=to_scheme_out(sch2, destination_groups=destination_groups, surcharges=surcharges),
        )
