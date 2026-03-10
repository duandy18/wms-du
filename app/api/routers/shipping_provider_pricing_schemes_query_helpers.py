# app/api/routers/shipping_provider_pricing_schemes_query_helpers.py
from __future__ import annotations

from typing import Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    DestinationGroupOut,
    SurchargeOut,
)
from app.api.routers.shipping_provider_pricing_schemes_mappers import (
    to_destination_group_out,
    to_surcharge_outs_from_config,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig


def load_scheme_entities(
    db: Session,
    scheme_id: int,
) -> Tuple[ShippingProviderPricingScheme, List[DestinationGroupOut], List[SurchargeOut]]:
    """
    读取 Scheme + DestinationGroups(+Provinces) + Surcharges，并组装为输出对象。
    surcharge 主线已切到：
      - shipping_provider_surcharge_configs
      - shipping_provider_surcharge_config_cities
    对外仍展平为兼容的 SurchargeOut 列表。
    """

    sch = (
        db.query(ShippingProviderPricingScheme)
        .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .one_or_none()
    )

    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    groups_raw = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .order_by(
            ShippingProviderDestinationGroup.sort_order.asc(),
            ShippingProviderDestinationGroup.id.asc(),
        )
        .all()
    )

    group_ids = [int(g.id) for g in groups_raw]

    provinces_by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}

    if group_ids:
        provinces = (
            db.query(ShippingProviderDestinationGroupMember)
            .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
            .order_by(
                ShippingProviderDestinationGroupMember.group_id.asc(),
                ShippingProviderDestinationGroupMember.province_code.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.province_name.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.id.asc(),
            )
            .all()
        )

        for p in provinces:
            provinces_by_group.setdefault(int(p.group_id), []).append(p)

    destination_groups: List[DestinationGroupOut] = []

    for g in groups_raw:
        destination_groups.append(
            to_destination_group_out(
                g,
                provinces_by_group.get(int(g.id), []),
            )
        )

    surcharge_configs = (
        db.query(ShippingProviderSurchargeConfig)
        .options(selectinload(ShippingProviderSurchargeConfig.cities))
        .filter(ShippingProviderSurchargeConfig.scheme_id == scheme_id)
        .order_by(ShippingProviderSurchargeConfig.id.asc())
        .all()
    )

    surcharges: List[SurchargeOut] = []
    for cfg in surcharge_configs:
        surcharges.extend(to_surcharge_outs_from_config(cfg))

    return sch, destination_groups, surcharges
