from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.module_resources_shared import (
    validate_scheme_publishable,
)
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
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_module_range import (
    ShippingProviderPricingSchemeModuleRange,
)
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def _validate_merged_billable_weight_fields(
    *,
    billable_weight_strategy: str,
    volume_divisor: int | None,
    rounding_mode: str,
    rounding_step_kg: float | None,
) -> None:
    if billable_weight_strategy == "actual_only":
        if volume_divisor is not None:
            raise HTTPException(
                status_code=422,
                detail="volume_divisor must be empty when billable_weight_strategy=actual_only",
            )

    if billable_weight_strategy == "max_actual_volume":
        if volume_divisor is None:
            raise HTTPException(
                status_code=422,
                detail="volume_divisor is required when billable_weight_strategy=max_actual_volume",
            )

    if rounding_mode == "none":
        if rounding_step_kg is not None:
            raise HTTPException(
                status_code=422,
                detail="rounding_step_kg must be empty when rounding_mode=none",
            )

    if rounding_mode == "ceil":
        if rounding_step_kg is None:
            raise HTTPException(
                status_code=422,
                detail="rounding_step_kg is required when rounding_mode=ceil",
            )


def _load_scheme_for_write_or_404(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    sch = (
        db.query(ShippingProviderPricingScheme)
        .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return sch


def _clone_scheme_tree(db: Session, source_scheme_id: int, target_scheme_id: int) -> None:
    source_ranges = (
        db.query(ShippingProviderPricingSchemeModuleRange)
        .filter(ShippingProviderPricingSchemeModuleRange.scheme_id == int(source_scheme_id))
        .order_by(
            ShippingProviderPricingSchemeModuleRange.sort_order.asc(),
            ShippingProviderPricingSchemeModuleRange.id.asc(),
        )
        .all()
    )

    source_groups = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == int(source_scheme_id))
        .order_by(
            ShippingProviderDestinationGroup.sort_order.asc(),
            ShippingProviderDestinationGroup.id.asc(),
        )
        .all()
    )
    source_group_ids = [int(g.id) for g in source_groups]

    source_members = []
    source_cells = []

    if source_group_ids:
        source_members = (
            db.query(ShippingProviderDestinationGroupMember)
            .filter(ShippingProviderDestinationGroupMember.group_id.in_(source_group_ids))
            .order_by(
                ShippingProviderDestinationGroupMember.group_id.asc(),
                ShippingProviderDestinationGroupMember.id.asc(),
            )
            .all()
        )
        source_cells = (
            db.query(ShippingProviderPricingMatrix)
            .filter(ShippingProviderPricingMatrix.group_id.in_(source_group_ids))
            .order_by(
                ShippingProviderPricingMatrix.group_id.asc(),
                ShippingProviderPricingMatrix.module_range_id.asc(),
                ShippingProviderPricingMatrix.id.asc(),
            )
            .all()
        )

    source_surcharges = (
        db.query(ShippingProviderSurcharge)
        .filter(ShippingProviderSurcharge.scheme_id == int(source_scheme_id))
        .order_by(ShippingProviderSurcharge.id.asc())
        .all()
    )

    range_id_map: dict[int, int] = {}
    group_id_map: dict[int, int] = {}

    for row in source_ranges:
        copied = ShippingProviderPricingSchemeModuleRange(
            scheme_id=int(target_scheme_id),
            min_kg=row.min_kg,
            max_kg=row.max_kg,
            sort_order=int(row.sort_order),
            default_pricing_mode=str(row.default_pricing_mode),
        )
        db.add(copied)
        db.flush()
        range_id_map[int(row.id)] = int(copied.id)

    for g in source_groups:
        copied = ShippingProviderDestinationGroup(
            scheme_id=int(target_scheme_id),
            name=str(g.name),
            sort_order=int(g.sort_order),
            active=bool(g.active),
        )
        db.add(copied)
        db.flush()
        group_id_map[int(g.id)] = int(copied.id)

    for m in source_members:
        db.add(
            ShippingProviderDestinationGroupMember(
                group_id=group_id_map[int(m.group_id)],
                province_code=m.province_code,
                province_name=m.province_name,
            )
        )

    for c in source_cells:
        db.add(
            ShippingProviderPricingMatrix(
                group_id=group_id_map[int(c.group_id)],
                module_range_id=range_id_map[int(c.module_range_id)],
                pricing_mode=str(c.pricing_mode),
                flat_amount=c.flat_amount,
                base_amount=c.base_amount,
                rate_per_kg=c.rate_per_kg,
                base_kg=c.base_kg,
                active=bool(c.active),
            )
        )

    for s in source_surcharges:
        db.add(
            ShippingProviderSurcharge(
                scheme_id=int(target_scheme_id),
                name=str(s.name),
                active=bool(s.active),
                scope=str(s.scope),
                province_code=s.province_code,
                city_code=s.city_code,
                province_name=s.province_name,
                city_name=s.city_name,
                fixed_amount=s.fixed_amount,
            )
        )

    db.flush()


def _archive_other_active_schemes(
    db: Session,
    *,
    provider_id: int,
    warehouse_id: int,
    keep_scheme_id: int,
) -> None:
    now = datetime.now(timezone.utc)

    db.execute(
        update(ShippingProviderPricingScheme)
        .where(
            ShippingProviderPricingScheme.shipping_provider_id == int(provider_id),
            ShippingProviderPricingScheme.warehouse_id == int(warehouse_id),
            ShippingProviderPricingScheme.id != int(keep_scheme_id),
            ShippingProviderPricingScheme.status == "active",
        )
        .values(
            status="archived",
            archived_at=now,
        )
    )


def register_update_routes(router: APIRouter) -> None:
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

        sch = _load_scheme_for_write_or_404(db, scheme_id)

        if str(sch.status) != "draft":
            raise HTTPException(status_code=400, detail="Only draft scheme can be modified")

        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            sch.name = norm_nonempty(data.get("name"), "name")

        if "currency" in data:
            sch.currency = str(data.get("currency") or "CNY").strip() or "CNY"

        if "effective_from" in data:
            sch.effective_from = data.get("effective_from")
        if "effective_to" in data:
            sch.effective_to = data.get("effective_to")

        if "default_pricing_mode" in data:
            try:
                sch.default_pricing_mode = validate_default_pricing_mode(data.get("default_pricing_mode"))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        if "billable_weight_strategy" in data:
            sch.billable_weight_strategy = str(data.get("billable_weight_strategy"))
        if "volume_divisor" in data:
            sch.volume_divisor = data.get("volume_divisor")
        if "rounding_mode" in data:
            sch.rounding_mode = str(data.get("rounding_mode"))
        if "rounding_step_kg" in data:
            sch.rounding_step_kg = data.get("rounding_step_kg")
        if "min_billable_weight_kg" in data:
            sch.min_billable_weight_kg = data.get("min_billable_weight_kg")

        validate_effective_window(sch.effective_from, sch.effective_to)

        _validate_merged_billable_weight_fields(
            billable_weight_strategy=str(sch.billable_weight_strategy),
            volume_divisor=sch.volume_divisor,
            rounding_mode=str(sch.rounding_mode),
            rounding_step_kg=sch.rounding_step_kg,
        )

        db.commit()
        db.refresh(sch)

        sch2, destination_groups, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(
            ok=True,
            data=to_scheme_out(sch2, destination_groups=destination_groups, surcharges=surcharges),
        )

    @router.post(
        "/pricing-schemes/{scheme_id}/clone",
        response_model=SchemeDetailOut,
        status_code=status.HTTP_201_CREATED,
    )
    def clone_scheme(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        source = _load_scheme_for_write_or_404(db, scheme_id)

        cloned = ShippingProviderPricingScheme(
            warehouse_id=int(source.warehouse_id),
            shipping_provider_id=int(source.shipping_provider_id),
            name=f"{source.name}-副本",
            status="draft",
            archived_at=None,
            currency=str(source.currency),
            default_pricing_mode=str(source.default_pricing_mode),
            billable_weight_strategy=str(source.billable_weight_strategy),
            volume_divisor=source.volume_divisor,
            rounding_mode=str(source.rounding_mode),
            rounding_step_kg=source.rounding_step_kg,
            min_billable_weight_kg=source.min_billable_weight_kg,
            effective_from=source.effective_from,
            effective_to=source.effective_to,
        )
        db.add(cloned)
        db.flush()

        _clone_scheme_tree(db, int(source.id), int(cloned.id))

        db.commit()
        db.refresh(cloned)

        sch2, destination_groups, surcharges = load_scheme_entities(db, int(cloned.id))
        return SchemeDetailOut(
            ok=True,
            data=to_scheme_out(sch2, destination_groups=destination_groups, surcharges=surcharges),
        )

    @router.post(
        "/pricing-schemes/{scheme_id}/publish",
        response_model=SchemeDetailOut,
    )
    def publish_scheme(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = _load_scheme_for_write_or_404(db, scheme_id)

        if str(sch.status) != "draft":
            raise HTTPException(status_code=400, detail="Only draft scheme can be published")

        validate_scheme_publishable(db, scheme_id=scheme_id)

        _archive_other_active_schemes(
            db,
            provider_id=int(sch.shipping_provider_id),
            warehouse_id=int(sch.warehouse_id),
            keep_scheme_id=int(sch.id),
        )

        sch.status = "active"
        sch.archived_at = None

        db.commit()
        db.refresh(sch)

        sch2, destination_groups, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(
            ok=True,
            data=to_scheme_out(sch2, destination_groups=destination_groups, surcharges=surcharges),
        )
