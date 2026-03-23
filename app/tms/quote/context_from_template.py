# app/tms/quote/context_from_template.py
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
)
from app.models.shipping_provider_pricing_template_matrix import (
    ShippingProviderPricingTemplateMatrix,
)
from app.models.shipping_provider_pricing_template_surcharge_config import (
    ShippingProviderPricingTemplateSurchargeConfig,
)

from .context import (
    QuoteCalcContext,
    QuoteGroupContext,
    QuoteGroupMemberContext,
    QuoteMatrixRowContext,
    QuoteSurchargeCityContext,
    QuoteSurchargeConfigContext,
)


def _to_float_or_none(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _load_template_or_404(
    db: Session,
    template_id: int,
) -> ShippingProviderPricingTemplate:
    row = (
        db.query(ShippingProviderPricingTemplate)
        .options(
            selectinload(ShippingProviderPricingTemplate.shipping_provider),
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
        raise ValueError("template not found")
    return row


def ensure_template_quotable(row: ShippingProviderPricingTemplate) -> None:
    if getattr(row, "archived_at", None) is not None or str(getattr(row, "status", "") or "") == "archived":
        raise ValueError("template archived")


def load_template_quote_context(
    db: Session,
    template_id: int,
) -> QuoteCalcContext:
    row = _load_template_or_404(db, int(template_id))
    ensure_template_quotable(row)

    provider_name = None
    if getattr(row, "shipping_provider", None) is not None:
        provider_name = getattr(row.shipping_provider, "name", None)

    groups = sorted(
        list(getattr(row, "destination_groups", []) or []),
        key=lambda x: (int(x.sort_order), int(x.id)),
    )

    group_contexts: list[QuoteGroupContext] = []
    matrix_contexts: list[QuoteMatrixRowContext] = []

    for group in groups:
        members = sorted(
            list(getattr(group, "members", []) or []),
            key=lambda x: (str(x.province_code or ""), str(x.province_name or ""), int(x.id)),
        )
        matrix_rows = sorted(
            list(getattr(group, "matrix_rows", []) or []),
            key=lambda x: (
                int(x.module_range.sort_order) if getattr(x, "module_range", None) is not None else 0,
                int(x.module_range_id),
                int(x.id),
            ),
        )

        group_contexts.append(
            QuoteGroupContext(
                id=int(group.id),
                name=str(group.name),
                active=bool(group.active),
                members=[
                    QuoteGroupMemberContext(
                        id=int(member.id),
                        province_code=member.province_code,
                        province_name=member.province_name,
                    )
                    for member in members
                ],
            )
        )

        for matrix_row in matrix_rows:
            mr = getattr(matrix_row, "module_range", None)
            if mr is None:
                raise ValueError(
                    f"template matrix row missing module_range (row_id={getattr(matrix_row, 'id', None)})"
                )

            matrix_contexts.append(
                QuoteMatrixRowContext(
                    id=int(matrix_row.id),
                    group_id=int(matrix_row.group_id),
                    module_range_id=int(matrix_row.module_range_id),
                    pricing_mode=str(matrix_row.pricing_mode),
                    flat_amount=_to_float_or_none(matrix_row.flat_amount),
                    base_amount=_to_float_or_none(matrix_row.base_amount),
                    rate_per_kg=_to_float_or_none(matrix_row.rate_per_kg),
                    base_kg=_to_float_or_none(matrix_row.base_kg),
                    active=bool(matrix_row.active),
                    min_kg=float(mr.min_kg),
                    max_kg=_to_float_or_none(mr.max_kg),
                )
            )

    surcharge_configs = sorted(
        list(getattr(row, "surcharge_configs", []) or []),
        key=lambda x: (str(x.province_code or ""), int(x.id)),
    )

    surcharge_contexts: list[QuoteSurchargeConfigContext] = []
    for cfg in surcharge_configs:
        cities = sorted(
            list(getattr(cfg, "cities", []) or []),
            key=lambda x: (str(x.city_code or ""), int(x.id)),
        )

        surcharge_contexts.append(
            QuoteSurchargeConfigContext(
                id=int(cfg.id),
                province_code=cfg.province_code,
                province_name=cfg.province_name,
                province_mode=str(cfg.province_mode),
                fixed_amount=float(cfg.fixed_amount),
                active=bool(cfg.active),
                cities=[
                    QuoteSurchargeCityContext(
                        id=int(city.id),
                        city_code=getattr(city, "city_code", None),
                        city_name=getattr(city, "city_name", None),
                        fixed_amount=float(city.fixed_amount),
                        active=bool(city.active),
                    )
                    for city in cities
                ],
            )
        )

    return QuoteCalcContext(
        template_id=int(row.id),
        shipping_provider_id=int(row.shipping_provider_id),
        shipping_provider_name=provider_name,
        template_name=str(row.name),
        status=str(row.status),
        archived_at=getattr(row, "archived_at", None),
        currency="CNY",
        billable_weight_strategy="actual_only",
        volume_divisor=None,
        rounding_mode="ceil",
        rounding_step_kg=1.0,
        min_billable_weight_kg=None,
        groups=group_contexts,
        matrix_rows=matrix_contexts,
        surcharge_configs=surcharge_contexts,
    )
