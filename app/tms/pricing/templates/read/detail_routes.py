from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
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
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.schemas.template import (
    TemplateDetailOut,
    TemplateOut,
)


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


def _load_template_or_404(
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


def register_detail_routes(router: APIRouter) -> None:
    @router.get(
        "/templates/{template_id}",
        response_model=TemplateDetailOut,
        name="pricing_template_detail",
    )
    def get_template_detail(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        row = _load_template_or_404(db, int(template_id))

        return TemplateDetailOut(
            ok=True,
            data=_to_template_out(row),
        )
