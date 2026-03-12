# app/api/routers/shipping_provider_pricing_schemes_mappers.py
from __future__ import annotations

from typing import List

from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    DestinationGroupOut,
    DestinationGroupProvinceOut,
    SchemeOut,
    SurchargeConfigCityOut,
    SurchargeConfigOut,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity


def to_destination_group_province_out(
    m: ShippingProviderDestinationGroupMember,
) -> DestinationGroupProvinceOut:
    return DestinationGroupProvinceOut(
        id=int(m.id),
        group_id=int(m.group_id),
        province_code=getattr(m, "province_code", None),
        province_name=getattr(m, "province_name", None),
    )


def to_destination_group_out(
    g: ShippingProviderDestinationGroup,
    provinces: List[ShippingProviderDestinationGroupMember],
    pricing_matrix: list[object] | None = None,
) -> DestinationGroupOut:
    return DestinationGroupOut(
        id=int(g.id),
        scheme_id=int(g.scheme_id),
        name=str(g.name),
        active=bool(g.active),
        provinces=[to_destination_group_province_out(x) for x in provinces],
    )


def to_surcharge_config_city_out(
    city_row: ShippingProviderSurchargeConfigCity,
) -> SurchargeConfigCityOut:
    return SurchargeConfigCityOut(
        id=int(city_row.id),
        config_id=int(city_row.config_id),
        city_code=str(city_row.city_code),
        city_name=getattr(city_row, "city_name", None),
        fixed_amount=city_row.fixed_amount,
        active=bool(city_row.active),
    )


def to_surcharge_config_out(
    cfg: ShippingProviderSurchargeConfig,
) -> SurchargeConfigOut:
    cities = [
        to_surcharge_config_city_out(city_row)
        for city_row in (getattr(cfg, "cities", []) or [])
    ]

    return SurchargeConfigOut(
        id=int(cfg.id),
        scheme_id=int(cfg.scheme_id),
        province_code=str(cfg.province_code),
        province_name=getattr(cfg, "province_name", None),
        province_mode=str(getattr(cfg, "province_mode", "province")),
        fixed_amount=cfg.fixed_amount,
        active=bool(cfg.active),
        cities=cities,
    )


def _must_get_shipping_provider_name(sch: ShippingProviderPricingScheme) -> str:
    sp = getattr(sch, "shipping_provider", None)
    name = getattr(sp, "name", None) if sp is not None else None
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(
            f"ShippingProvider name is required for scheme_id={sch.id} "
            f"shipping_provider_id={sch.shipping_provider_id}"
        )
    return name.strip()


def to_scheme_out(
    sch: ShippingProviderPricingScheme,
    destination_groups: List[DestinationGroupOut] | None = None,
    surcharge_configs: List[SurchargeConfigOut] | None = None,
) -> SchemeOut:
    dpm = getattr(sch, "default_pricing_mode", "linear_total")

    return SchemeOut(
        id=int(sch.id),
        shipping_provider_id=int(sch.shipping_provider_id),
        shipping_provider_name=_must_get_shipping_provider_name(sch),
        name=str(sch.name),
        status=str(getattr(sch, "status", "draft")),
        archived_at=getattr(sch, "archived_at", None),
        currency=str(sch.currency),
        effective_from=getattr(sch, "effective_from", None),
        effective_to=getattr(sch, "effective_to", None),
        default_pricing_mode=str(dpm),
        billable_weight_strategy=str(getattr(sch, "billable_weight_strategy", "actual_only")),
        volume_divisor=getattr(sch, "volume_divisor", None),
        rounding_mode=str(getattr(sch, "rounding_mode", "none")),
        rounding_step_kg=(
            None if getattr(sch, "rounding_step_kg", None) is None else float(sch.rounding_step_kg)
        ),
        min_billable_weight_kg=(
            None if getattr(sch, "min_billable_weight_kg", None) is None else float(sch.min_billable_weight_kg)
        ),
        destination_groups=destination_groups or [],
        surcharge_configs=surcharge_configs or [],
    )
