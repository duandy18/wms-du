from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

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
from app.models.warehouse_shipping_provider import WarehouseShippingProvider
from app.tms.pricing.templates.schemas.template import TemplateOut


@dataclass(frozen=True)
class TemplateStats:
    used_binding_count: int
    ranges_count: int
    groups_count: int
    matrix_cells_count: int
    config_status: str


@dataclass(frozen=True)
class TemplateCapabilities:
    can_edit_structure: bool
    can_submit_validation: bool
    can_clone: bool
    can_archive: bool
    readonly_reason: str | None


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


def _base_query(db: Session):
    return db.query(ShippingProviderPricingTemplate).options(
        selectinload(ShippingProviderPricingTemplate.shipping_provider)
    )


def _compute_expected_matrix_cells_count(
    *,
    expected_ranges_count: int,
    expected_groups_count: int,
) -> int:
    return int(expected_ranges_count) * int(expected_groups_count)


def _compute_config_status(
    *,
    expected_ranges_count: int,
    expected_groups_count: int,
    ranges_count: int,
    groups_count: int,
    matrix_cells_count: int,
) -> str:
    if ranges_count == 0 and groups_count == 0 and matrix_cells_count == 0:
        return "empty"

    expected_matrix_cells_count = _compute_expected_matrix_cells_count(
        expected_ranges_count=expected_ranges_count,
        expected_groups_count=expected_groups_count,
    )

    if (
        ranges_count == expected_ranges_count
        and groups_count == expected_groups_count
        and matrix_cells_count == expected_matrix_cells_count
    ):
        return "ready"

    return "incomplete"


def build_template_capabilities(
    *,
    template: ShippingProviderPricingTemplate,
    stats: TemplateStats,
) -> TemplateCapabilities:
    status = str(template.status or "")
    validation_status = str(template.validation_status or "")
    source_template_id = getattr(template, "source_template_id", None)

    is_draft = status == "draft"
    is_archived = status == "archived"
    is_validated = validation_status == "passed"
    is_cloned_template = source_template_id is not None

    readonly_reason: str | None = None
    if is_archived:
        readonly_reason = "archived_template"
    elif is_validated:
        readonly_reason = "validated_template"
    elif is_cloned_template:
        readonly_reason = "cloned_template_structure_locked"

    can_edit_structure = is_draft and not is_validated and not is_cloned_template
    can_submit_validation = (
        is_draft
        and not is_validated
        and str(stats.config_status) == "ready"
        and int(stats.used_binding_count) == 0
    )
    can_clone = True
    can_archive = is_draft and int(stats.used_binding_count) == 0

    return TemplateCapabilities(
        can_edit_structure=can_edit_structure,
        can_submit_validation=can_submit_validation,
        can_clone=can_clone,
        can_archive=can_archive,
        readonly_reason=readonly_reason,
    )


def _serialize_template_capabilities(
    caps: TemplateCapabilities,
) -> dict[str, object]:
    return {
        "can_edit_structure": bool(caps.can_edit_structure),
        "can_submit_validation": bool(caps.can_submit_validation),
        "can_clone": bool(caps.can_clone),
        "can_archive": bool(caps.can_archive),
        "readonly_reason": caps.readonly_reason,
    }


def _build_template_stats_map(
    db: Session,
    *,
    template_ids: list[int],
) -> dict[int, TemplateStats]:
    if not template_ids:
        return {}

    range_rows = (
        db.query(
            ShippingProviderPricingTemplateModuleRange.template_id,
            func.count(ShippingProviderPricingTemplateModuleRange.id),
        )
        .filter(ShippingProviderPricingTemplateModuleRange.template_id.in_(template_ids))
        .group_by(ShippingProviderPricingTemplateModuleRange.template_id)
        .all()
    )
    ranges_map = {int(template_id): int(count or 0) for template_id, count in range_rows}

    group_rows = (
        db.query(
            ShippingProviderPricingTemplateDestinationGroup.template_id,
            func.count(ShippingProviderPricingTemplateDestinationGroup.id),
        )
        .filter(ShippingProviderPricingTemplateDestinationGroup.template_id.in_(template_ids))
        .group_by(ShippingProviderPricingTemplateDestinationGroup.template_id)
        .all()
    )
    groups_map = {int(template_id): int(count or 0) for template_id, count in group_rows}

    matrix_rows = (
        db.query(
            ShippingProviderPricingTemplateDestinationGroup.template_id,
            func.count(ShippingProviderPricingTemplateMatrix.id),
        )
        .outerjoin(
            ShippingProviderPricingTemplateMatrix,
            ShippingProviderPricingTemplateMatrix.group_id
            == ShippingProviderPricingTemplateDestinationGroup.id,
        )
        .filter(ShippingProviderPricingTemplateDestinationGroup.template_id.in_(template_ids))
        .group_by(ShippingProviderPricingTemplateDestinationGroup.template_id)
        .all()
    )
    matrix_map = {int(template_id): int(count or 0) for template_id, count in matrix_rows}

    binding_rows = (
        db.query(
            WarehouseShippingProvider.active_template_id,
            func.count(WarehouseShippingProvider.id),
        )
        .filter(WarehouseShippingProvider.active_template_id.in_(template_ids))
        .group_by(WarehouseShippingProvider.active_template_id)
        .all()
    )
    bindings_map = {int(template_id): int(count or 0) for template_id, count in binding_rows}

    templates = (
        db.query(
            ShippingProviderPricingTemplate.id,
            ShippingProviderPricingTemplate.expected_ranges_count,
            ShippingProviderPricingTemplate.expected_groups_count,
        )
        .filter(ShippingProviderPricingTemplate.id.in_(template_ids))
        .all()
    )
    expected_map = {
        int(row.id): (
            int(row.expected_ranges_count),
            int(row.expected_groups_count),
        )
        for row in templates
    }

    out: dict[int, TemplateStats] = {}
    for template_id in template_ids:
        ranges_count = int(ranges_map.get(template_id, 0))
        groups_count = int(groups_map.get(template_id, 0))
        matrix_cells_count = int(matrix_map.get(template_id, 0))
        used_binding_count = int(bindings_map.get(template_id, 0))
        expected_ranges_count, expected_groups_count = expected_map.get(
            int(template_id),
            (0, 0),
        )
        config_status = _compute_config_status(
            expected_ranges_count=expected_ranges_count,
            expected_groups_count=expected_groups_count,
            ranges_count=ranges_count,
            groups_count=groups_count,
            matrix_cells_count=matrix_cells_count,
        )
        out[int(template_id)] = TemplateStats(
            used_binding_count=used_binding_count,
            ranges_count=ranges_count,
            groups_count=groups_count,
            matrix_cells_count=matrix_cells_count,
            config_status=config_status,
        )
    return out


def build_template_stats(
    db: Session,
    *,
    template_id: int,
) -> TemplateStats:
    stats_map = _build_template_stats_map(db, template_ids=[int(template_id)])
    return stats_map.get(
        int(template_id),
        TemplateStats(
            used_binding_count=0,
            ranges_count=0,
            groups_count=0,
            matrix_cells_count=0,
            config_status="empty",
        ),
    )


def load_template_or_404(
    db: Session,
    *,
    template_id: int,
) -> ShippingProviderPricingTemplate:
    row = (
        _base_query(db)
        .filter(ShippingProviderPricingTemplate.id == int(template_id))
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="PricingTemplate not found")
    return row


def load_template_detail_or_404(
    db: Session,
    *,
    template_id: int,
) -> ShippingProviderPricingTemplate:
    row = (
        _base_query(db)
        .options(
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


def serialize_template_out(
    template: ShippingProviderPricingTemplate,
    *,
    include_detail: bool,
    stats: TemplateStats | None = None,
) -> TemplateOut:
    provider_name = ""
    if getattr(template, "shipping_provider", None) is not None:
        provider_name = getattr(template.shipping_provider, "name", "") or ""

    destination_groups = []
    surcharge_configs = []

    if include_detail:
        destination_groups = sorted(
            list(getattr(template, "destination_groups", []) or []),
            key=lambda x: (int(x.sort_order), int(x.id)),
        )
        surcharge_configs = sorted(
            list(getattr(template, "surcharge_configs", []) or []),
            key=lambda x: (str(x.province_code), int(x.id)),
        )

    expected_ranges_count = int(template.expected_ranges_count)
    expected_groups_count = int(template.expected_groups_count)
    expected_matrix_cells_count = _compute_expected_matrix_cells_count(
        expected_ranges_count=expected_ranges_count,
        expected_groups_count=expected_groups_count,
    )

    if stats is None:
        if include_detail:
            ranges_count = len(list(getattr(template, "ranges", []) or []))
            groups_count = len(destination_groups)
            matrix_cells_count = sum(len(list(getattr(g, "matrix_rows", []) or [])) for g in destination_groups)
            stats = TemplateStats(
                used_binding_count=0,
                ranges_count=ranges_count,
                groups_count=groups_count,
                matrix_cells_count=matrix_cells_count,
                config_status=_compute_config_status(
                    expected_ranges_count=expected_ranges_count,
                    expected_groups_count=expected_groups_count,
                    ranges_count=ranges_count,
                    groups_count=groups_count,
                    matrix_cells_count=matrix_cells_count,
                ),
            )
        else:
            stats = TemplateStats(
                used_binding_count=0,
                ranges_count=0,
                groups_count=0,
                matrix_cells_count=0,
                config_status="empty",
            )

    capabilities = build_template_capabilities(
        template=template,
        stats=stats,
    )

    return TemplateOut(
        id=int(template.id),
        shipping_provider_id=int(template.shipping_provider_id),
        shipping_provider_name=provider_name,
        source_template_id=(
            int(template.source_template_id)
            if getattr(template, "source_template_id", None) is not None
            else None
        ),
        name=template.name,
        expected_ranges_count=expected_ranges_count,
        expected_groups_count=expected_groups_count,
        expected_matrix_cells_count=expected_matrix_cells_count,
        status=template.status,
        archived_at=template.archived_at,
        validation_status=template.validation_status,
        created_at=template.created_at,
        updated_at=template.updated_at,
        used_binding_count=int(stats.used_binding_count),
        config_status=str(stats.config_status),
        ranges_count=int(stats.ranges_count),
        groups_count=int(stats.groups_count),
        matrix_cells_count=int(stats.matrix_cells_count),
        capabilities=_serialize_template_capabilities(capabilities),
        destination_groups=[_serialize_group(g) for g in destination_groups],
        surcharge_configs=[_serialize_surcharge_config(c) for c in surcharge_configs],
    )


def list_templates(
    db: Session,
    *,
    shipping_provider_id: int | None = None,
    status: str | None = None,
    include_archived: bool = False,
) -> list[TemplateOut]:
    q = _base_query(db)

    if shipping_provider_id is not None:
        q = q.filter(ShippingProviderPricingTemplate.shipping_provider_id == shipping_provider_id)

    if status is not None:
        q = q.filter(ShippingProviderPricingTemplate.status == status)

    if not include_archived:
        q = q.filter(ShippingProviderPricingTemplate.archived_at.is_(None))

    rows = q.order_by(ShippingProviderPricingTemplate.id.desc()).all()
    template_ids = [int(row.id) for row in rows]
    stats_map = _build_template_stats_map(db, template_ids=template_ids)

    return [
        serialize_template_out(
            row,
            include_detail=False,
            stats=stats_map.get(
                int(row.id),
                TemplateStats(
                    used_binding_count=0,
                    ranges_count=0,
                    groups_count=0,
                    matrix_cells_count=0,
                    config_status="empty",
                ),
            ),
        )
        for row in rows
    ]


def list_bindable_templates(
    db: Session,
    *,
    shipping_provider_id: int,
) -> list[TemplateOut]:
    rows = list_templates(
        db,
        shipping_provider_id=int(shipping_provider_id),
        include_archived=False,
    )

    return [
        row
        for row in rows
        if row.archived_at is None
        and str(row.status) == "draft"
        and str(row.validation_status) == "passed"
        and str(row.config_status) == "ready"
        and int(row.used_binding_count) == 0
    ]


def count_template_used_bindings(
    db: Session,
    *,
    template_id: int,
) -> int:
    return int(build_template_stats(db, template_id=int(template_id)).used_binding_count)


def is_template_bound(
    db: Session,
    *,
    template_id: int,
) -> bool:
    return count_template_used_bindings(db, template_id=template_id) > 0
