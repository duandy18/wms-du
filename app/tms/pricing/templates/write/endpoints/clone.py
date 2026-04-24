from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, selectinload

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.pricing.templates.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.pricing.templates.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_destination_group_member import (
    ShippingProviderPricingTemplateDestinationGroupMember,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_matrix import (
    ShippingProviderPricingTemplateMatrix,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_module_range import (
    ShippingProviderPricingTemplateModuleRange,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_surcharge_config import (
    ShippingProviderPricingTemplateSurchargeConfig,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_surcharge_config_city import (
    ShippingProviderPricingTemplateSurchargeConfigCity,
)
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.repository import build_template_stats, serialize_template_out
from app.tms.pricing.templates.contracts.template import (
    TemplateCloneIn,
    TemplateDetailOut,
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


def _derive_clone_expected_counts(
    source: ShippingProviderPricingTemplate,
) -> tuple[int, int]:
    actual_ranges_count = len(list(getattr(source, "ranges", []) or []))
    actual_groups_count = len(list(getattr(source, "destination_groups", []) or []))

    expected_ranges_count = (
        actual_ranges_count
        if actual_ranges_count > 0
        else int(source.expected_ranges_count)
    )
    expected_groups_count = (
        actual_groups_count
        if actual_groups_count > 0
        else int(source.expected_groups_count)
    )

    if expected_ranges_count <= 0:
        raise HTTPException(
            status_code=400,
            detail="Source template has invalid expected_ranges_count for clone",
        )
    if expected_groups_count <= 0:
        raise HTTPException(
            status_code=400,
            detail="Source template has invalid expected_groups_count for clone",
        )

    return expected_ranges_count, expected_groups_count


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
        expected_ranges_count, expected_groups_count = _derive_clone_expected_counts(source)

        cloned = ShippingProviderPricingTemplate(
            shipping_provider_id=int(source.shipping_provider_id),
            source_template_id=int(source.id),
            name=_norm_nonempty(payload.name, "name") if payload.name else f"{source.name}-副本",
            expected_ranges_count=int(expected_ranges_count),
            expected_groups_count=int(expected_groups_count),
            status="draft",
            archived_at=None,
            validation_status="not_validated",
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

        stats = build_template_stats(db, template_id=int(cloned.id))

        return TemplateDetailOut(
            ok=True,
            data=serialize_template_out(cloned_reloaded, include_detail=True, stats=stats),
        )
