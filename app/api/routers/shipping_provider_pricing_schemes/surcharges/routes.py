# app/api/routers/shipping_provider_pricing_schemes/surcharges/routes.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_surcharge_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SurchargeCreateIn,
    SurchargeOut,
    SurchargeUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes.schemas.surcharge import SurchargeUpsertIn
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, norm_nonempty
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .helpers import (
    ensure_dest_mutual_exclusion,
    normalize_scope,
)


def _same_key(
    row: ShippingProviderSurcharge,
    *,
    scope: str,
    province_name: str | None,
    city_name: str | None,
) -> bool:
    return (
        str(row.scope) == scope
        and ((row.province_name or None) == (province_name or None))
        and ((row.city_name or None) == (city_name or None))
    )


def _require_scheme(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return sch


def register_surcharges_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/surcharges",
        response_model=SurchargeOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_surcharge(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        scope2 = normalize_scope(payload.scope)

        ensure_dest_mutual_exclusion(
            db,
            scheme_id=scheme_id,
            target_scope=scope2,
            province_code=payload.province_code,
            province_name=payload.province_name,
            target_id=None,
            active=bool(payload.active),
        )

        s = ShippingProviderSurcharge(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
            priority=int(payload.priority),
            scope=scope2,
            stackable=bool(payload.stackable),
            province_code=payload.province_code,
            city_code=payload.city_code,
            province_name=payload.province_name,
            city_name=payload.city_name,
            fixed_amount=payload.fixed_amount,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.post(
        "/pricing-schemes/{scheme_id}/surcharges:upsert",
        response_model=SurchargeOut,
        status_code=status.HTTP_200_OK,
    )
    def upsert_surcharge(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeUpsertIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        终态主入口：
        - 结构化 province/city fixed surcharge
        - 同 key 则更新，否则创建
        """
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        scope2 = payload.scope
        province_name2 = payload.province_name
        city_name2 = payload.city_name if payload.scope == "city" else None

        ensure_dest_mutual_exclusion(
            db,
            scheme_id=scheme_id,
            target_scope=scope2,
            province_code=payload.province_code,
            province_name=province_name2,
            target_id=None,
            active=bool(payload.active),
        )

        rows = (
            db.query(ShippingProviderSurcharge)
            .filter(ShippingProviderSurcharge.scheme_id == scheme_id)
            .order_by(ShippingProviderSurcharge.id.asc())
            .all()
        )

        target: ShippingProviderSurcharge | None = None
        for s in rows:
            if _same_key(
                s,
                scope=scope2,
                province_name=province_name2,
                city_name=city_name2,
            ):
                target = s
                break

        name = payload.name.strip() if isinstance(payload.name, str) and payload.name.strip() else None
        if not name:
            name = province_name2 if scope2 == "province" else f"{province_name2}-{city_name2}"

        if target is None:
            s = ShippingProviderSurcharge(
                scheme_id=scheme_id,
                name=norm_nonempty(name, "name"),
                active=bool(payload.active),
                priority=int(payload.priority),
                scope=scope2,
                stackable=bool(payload.stackable),
                province_code=payload.province_code,
                city_code=payload.city_code if scope2 == "city" else None,
                province_name=province_name2,
                city_name=city_name2,
                fixed_amount=Decimal(payload.amount),
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            return to_surcharge_out(s)

        ensure_dest_mutual_exclusion(
            db,
            scheme_id=scheme_id,
            target_scope=scope2,
            province_code=payload.province_code,
            province_name=province_name2,
            target_id=int(target.id),
            active=bool(payload.active),
        )

        target.name = norm_nonempty(name, "name")
        target.active = bool(payload.active)
        target.priority = int(payload.priority)
        target.scope = scope2
        target.stackable = bool(payload.stackable)
        target.province_code = payload.province_code
        target.city_code = payload.city_code if scope2 == "city" else None
        target.province_name = province_name2
        target.city_name = city_name2
        target.fixed_amount = Decimal(payload.amount)
        db.commit()
        db.refresh(target)
        return to_surcharge_out(target)

    @router.patch(
        "/surcharges/{surcharge_id}",
        response_model=SurchargeOut,
    )
    def update_surcharge(
        surcharge_id: int = Path(..., ge=1),
        payload: SurchargeUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        data = payload.model_dump(exclude_unset=True)

        next_scope = normalize_scope(data.get("scope", s.scope))
        next_active = bool(data["active"]) if "active" in data else bool(s.active)

        next_province_code = data.get("province_code", s.province_code)
        next_city_code = data.get("city_code", s.city_code)
        next_province_name = data.get("province_name", s.province_name)
        next_city_name = data.get("city_name", s.city_name)

        next_fixed_amount = data.get("fixed_amount", s.fixed_amount)

        ensure_dest_mutual_exclusion(
            db,
            scheme_id=int(s.scheme_id),
            target_scope=next_scope,
            province_code=next_province_code,
            province_name=next_province_name,
            target_id=int(s.id),
            active=next_active,
        )

        if next_fixed_amount is None:
            raise HTTPException(status_code=422, detail="fixed_amount is required")

        if "name" in data:
            s.name = norm_nonempty(data.get("name"), "name")
        if "active" in data:
            s.active = bool(data["active"])
        if "priority" in data and data["priority"] is not None:
            s.priority = int(data["priority"])
        if "scope" in data and data["scope"] is not None:
            s.scope = next_scope
        if "stackable" in data and data["stackable"] is not None:
            s.stackable = bool(data["stackable"])

        if "province_code" in data:
            s.province_code = next_province_code
        if "city_code" in data:
            s.city_code = next_city_code
        if "province_name" in data:
            s.province_name = next_province_name
        if "city_name" in data:
            s.city_name = next_city_name

        if "fixed_amount" in data:
            s.fixed_amount = next_fixed_amount

        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.delete(
        "/surcharges/{surcharge_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_surcharge(
        surcharge_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        if bool(s.active):
            raise HTTPException(status_code=409, detail="must disable surcharge before delete")

        db.delete(s)
        db.commit()
        return {"ok": True}
