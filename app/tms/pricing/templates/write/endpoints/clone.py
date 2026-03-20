from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
)
from app.models.shipping_provider_pricing_template_destination_group_member import (
    ShippingProviderPricingTemplateDestinationGroupMember,
)
from app.models.shipping_provider_pricing_template_matrix import (
    ShippingProviderPricingTemplateMatrix,
)
from app.models.shipping_provider_pricing_template_module_range import (
    ShippingProviderPricingTemplateModuleRange,
)
from app.models.shipping_provider_pricing_template_surcharge_config import (
    ShippingProviderPricingTemplateSurchargeConfig,
)
from app.models.shipping_provider_pricing_template_surcharge_config_city import (
    ShippingProviderPricingTemplateSurchargeConfigCity,
)
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.schemas.template import (
    TemplateCloneIn,
    TemplateDetailOut,
    TemplateOut,
)


def _norm_nonempty(value: str | None, field_name: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return v


def _load_template_for_clone_or_404(
    db: Session,
    template_id: int,
) -> ShippingProviderPricingTemplate:
    row = (
        db.query(ShippingProviderPricingTemplate)
        .options(
            selectinload(ShippingProviderPricingTemplate.shipping_provider),
            selectinload(ShippingProviderPricingTemplate.ranges),
            selectinload(ShippingProviderPricingTemplate.destination_groups).selectinload(
                ShippingProviderPricingTemplateDestinationGroup.members
            ),
            selectinload(ShippingProviderPricingTemplate.destination_groups).selectinload(
                ShippingProviderPricingTemplateDestinationGroup.matrix_rows
            ).selectinload(ShippingProviderPricingTemplateMatrix.module_range),
            selectinload(ShippingProviderPricingTemplate.surcharge_configs).selectinload(
                ShippingProviderPricingTemplateSurchargeConfig.cities
            ),
        )
        .filter(ShippingProviderPricingTemplate.id == int(template_id))
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="PricingTemplate not found")
    return row


def _clone_template_tree(
    db: Session,
    *,
    source: ShippingProviderPricingTemplate,
    target_template_id: int,
) -> None:
    source_ranges = sorted(
        list(getattr(source, "ranges", []) or []),
        key=lambda x: (int(x.sort_order), int(x.id)),
    )
    source_groups = sorted(
        list(getattr(source, "destination_groups", []) or []),
        key=lambda x: (int(x.sort_order), int(x.id)),
    )
    source_surcharge_configs = sorted(
        list(getattr(source, "surcharge_configs", []) or []),
        key=lambda x: (str(x.province_code), int(x.id)),
    )

    range_id_map: dict[int, int] = {}
    group_id_map: dict[int, int] = {}

    for row in source_ranges:
        copied = ShippingProviderPricingTemplateModuleRange(
            template_id=int(target_template_id),
            min_kg=row.min_kg,
            max_kg=row.max_kg,
            sort_order=int(row.sort_order),
            default_pricing_mode=str(row.default_pricing_mode),
        )
        db.add(copied)
        db.flush()
        range_id_map[int(row.id)] = int(copied.id)

    for group in source_groups:
        copied_group = ShippingProviderPricingTemplateDestinationGroup(
            template_id=int(target_template_id),
            name=str(group.name),
            sort_order=int(group.sort_order),
            active=bool(group.active),
        )
        db.add(copied_group)
        db.flush()
        group_id_map[int(group.id)] = int(copied_group.id)

        members = sorted(
            list(getattr(group, "members", []) or []),
            key=lambda x: (str(x.province_code or ""), str(x.province_name or ""), int(x.id)),
        )
        for member in members:
            db.add(
                ShippingProviderPricingTemplateDestinationGroupMember(
                    group_id=int(copied_group.id),
                    province_code=member.province_code,
                    province_name=member.province_name,
                )
            )

    for group in source_groups:
        matrix_rows = sorted(
            list(getattr(group, "matrix_rows", []) or []),
            key=lambda x: (
                int(x.module_range.sort_order) if getattr(x, "module_range", None) is not None else 0,
                int(x.module_range_id),
                int(x.id),
            ),
        )
        for row in matrix_rows:
            mapped_range_id = range_id_map.get(int(row.module_range_id))
            mapped_group_id = group_id_map.get(int(group.id))
            if mapped_range_id is None or mapped_group_id is None:
                raise HTTPException(status_code=500, detail="template clone range/group map broken")

            db.add(
                ShippingProviderPricingTemplateMatrix(
                    group_id=int(mapped_group_id),
                    pricing_mode=str(row.pricing_mode),
                    flat_amount=row.flat_amount,
                    base_amount=row.base_amount,
                    rate_per_kg=row.rate_per_kg,
                    base_kg=row.base_kg,
                    active=bool(row.active),
                    module_range_id=int(mapped_range_id),
                )
            )

    for cfg in source_surcharge_configs:
        copied_cfg = ShippingProviderPricingTemplateSurchargeConfig(
            template_id=int(target_template_id),
            province_code=str(cfg.province_code),
            province_name=cfg.province_name,
            province_mode=str(cfg.province_mode),
            fixed_amount=cfg.fixed_amount,
            active=bool(cfg.active),
        )
        db.add(copied_cfg)
        db.flush()

        cities = sorted(
            list(getattr(cfg, "cities", []) or []),
            key=lambda x: (str(x.city_code), int(x.id)),
        )
        for city in cities:
            db.add(
                ShippingProviderPricingTemplateSurchargeConfigCity(
                    config_id=int(copied_cfg.id),
                    city_code=str(city.city_code),
                    city_name=city.city_name,
                    fixed_amount=city.fixed_amount,
                    active=bool(city.active),
                )
            )

    db.flush()


def _serialize_range(
    row: ShippingProviderPricingTemplateModuleRange,
) -> dict[str, object]:
    return {
        "id": int(row.id),
        "template_id": int(row.template_id),
        "min_kg": float(row.min_kg),
        "max_kg": float(row.max_kg) if row.max_kg is not None else None,
        "sort_order": int(row.sort_order),
        "default_pricing_mode": str(row.default_pricing_mode),
    }


def _serialize_matrix_row(
    row: ShippingProviderPricingTemplateMatrix,
) -> dict[str, object]:
    return {
        "id": int(row.id),
        "group_id": int(row.group_id),
        "module_range_id": int(row.module_range_id),
        "pricing_mode": str(row.pricing_mode),
        "flat_amount": float(row.flat_amount) if row.flat_amount is not None else None,
        "base_amount": float(row.base_amount) if row.base_amount is not None else None,
        "rate_per_kg": float(row.rate_per_kg) if row.rate_per_kg is not None else None,
        "base_kg": float(row.base_kg) if row.base_kg is not None else None,
        "active": bool(row.active),
        "module_range": _serialize_range(row.module_range) if row.module_range is not None else None,
    }


def _serialize_group(
    row: ShippingProviderPricingTemplateDestinationGroup,
) -> dict[str, object]:
    members = sorted(
        list(getattr(row, "members", []) or []),
        key=lambda x: (str(x.province_code or ""), str(x.province_name or ""), int(x.id)),
    )
    matrix_rows = sorted(
        list(getattr(row, "matrix_rows", []) or []),
        key=lambda x: (
            int(x.module_range.sort_order) if getattr(x, "module_range", None) is not None else 0,
            int(x.module_range_id),
            int(x.id),
        ),
    )

    return {
        "id": int(row.id),
        "template_id": int(row.template_id),
        "name": str(row.name),
        "sort_order": int(row.sort_order),
        "active": bool(row.active),
        "members": [
            {
                "id": int(m.id),
                "group_id": int(m.group_id),
                "province_code": m.province_code,
                "province_name": m.province_name,
            }
            for m in members
        ],
        "matrix_rows": [_serialize_matrix_row(m) for m in matrix_rows],
    }


def _serialize_surcharge_config(
    row: ShippingProviderPricingTemplateSurchargeConfig,
) -> dict[str, object]:
    cities = sorted(
        list(getattr(row, "cities", []) or []),
        key=lambda x: (str(x.city_code), int(x.id)),
    )

    return {
        "id": int(row.id),
        "template_id": int(row.template_id),
        "province_code": str(row.province_code),
        "province_name": row.province_name,
        "province_mode": str(row.province_mode),
        "fixed_amount": float(row.fixed_amount),
        "active": bool(row.active),
        "cities": [
            {
                "id": int(city.id),
                "config_id": int(city.config_id),
                "city_code": str(city.city_code),
                "city_name": city.city_name,
                "fixed_amount": float(city.fixed_amount),
                "active": bool(city.active),
            }
            for city in cities
        ],
    }


def _to_template_out(template: ShippingProviderPricingTemplate) -> TemplateOut:
    provider_name = ""
    if getattr(template, "shipping_provider", None) is not None:
        provider_name = getattr(template.shipping_provider, "name", "") or ""

    destination_groups = sorted(
        list(getattr(template, "destination_groups", []) or []),
        key=lambda x: (int(x.sort_order), int(x.id)),
    )
    surcharge_configs = sorted(
        list(getattr(template, "surcharge_configs", []) or []),
        key=lambda x: (str(x.province_code), int(x.id)),
    )

    return TemplateOut(
        id=int(template.id),
        shipping_provider_id=int(template.shipping_provider_id),
        shipping_provider_name=provider_name,
        name=template.name,
        status=template.status,
        archived_at=template.archived_at,
        currency=template.currency,
        effective_from=template.effective_from,
        effective_to=template.effective_to,
        default_pricing_mode=template.default_pricing_mode,
        billable_weight_strategy=template.billable_weight_strategy,
        volume_divisor=template.volume_divisor,
        rounding_mode=template.rounding_mode,
        rounding_step_kg=(
            float(template.rounding_step_kg)
            if template.rounding_step_kg is not None
            else None
        ),
        min_billable_weight_kg=(
            float(template.min_billable_weight_kg)
            if template.min_billable_weight_kg is not None
            else None
        ),
        destination_groups=[_serialize_group(g) for g in destination_groups],
        surcharge_configs=[_serialize_surcharge_config(c) for c in surcharge_configs],
    )


def register_clone_routes(router: APIRouter) -> None:
    @router.post(
        "/templates/{template_id}/clone",
        response_model=TemplateDetailOut,
        status_code=status.HTTP_201_CREATED,
        name="pricing_template_clone",
    )
    def clone_template(
        template_id: int = Path(..., ge=1),
        payload: TemplateCloneIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        source = _load_template_for_clone_or_404(db, int(template_id))

        cloned = ShippingProviderPricingTemplate(
            shipping_provider_id=int(source.shipping_provider_id),
            name=_norm_nonempty(payload.name, "name") if payload.name else f"{source.name}-副本",
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

        _clone_template_tree(
            db,
            source=source,
            target_template_id=int(cloned.id),
        )

        db.commit()

        cloned_reloaded = _load_template_for_clone_or_404(db, int(cloned.id))
        if getattr(cloned_reloaded, "shipping_provider", None) is None:
            cloned_reloaded.shipping_provider = source.shipping_provider

        return TemplateDetailOut(
            ok=True,
            data=_to_template_out(cloned_reloaded),
        )
