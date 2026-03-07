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
    to_surcharge_out,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def load_scheme_entities(
    db: Session,
    scheme_id: int,
) -> Tuple[ShippingProviderPricingScheme, List[DestinationGroupOut], List[SurchargeOut]]:
    """
    读取 Scheme + DestinationGroups(+Members,+PricingMatrix) + Surcharges，并组装为输出对象。
    - 只做查询与组装，不做权限校验
    - scheme 不存在则抛 404
    - shipping_provider_name 必须由后端真实关联提供
    """
    sch = (
        db.query(ShippingProviderPricingScheme)
        .options(
            selectinload(ShippingProviderPricingScheme.shipping_provider),
        )
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    sp = getattr(sch, "shipping_provider", None)
    sp_name = getattr(sp, "name", None) if sp is not None else None
    if not isinstance(sp_name, str) or not sp_name.strip():
        raise HTTPException(
            status_code=500,
            detail=(
                f"Scheme shipping provider missing/invalid "
                f"(scheme_id={scheme_id}, shipping_provider_id={sch.shipping_provider_id})"
            ),
        )

    groups_raw = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .order_by(ShippingProviderDestinationGroup.id.asc())
        .all()
    )
    group_ids = [g.id for g in groups_raw]

    members_by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
    matrix_by_group: Dict[int, List[ShippingProviderPricingMatrix]] = {}

    if group_ids:
        members = (
            db.query(ShippingProviderDestinationGroupMember)
            .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
            .order_by(
                ShippingProviderDestinationGroupMember.group_id.asc(),
                ShippingProviderDestinationGroupMember.scope.asc(),
                ShippingProviderDestinationGroupMember.province_code.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.city_code.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.province_name.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.city_name.asc().nulls_last(),
                ShippingProviderDestinationGroupMember.id.asc(),
            )
            .all()
        )
        for m in members:
            members_by_group.setdefault(m.group_id, []).append(m)

        matrix_rows = (
            db.query(ShippingProviderPricingMatrix)
            .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
            .order_by(
                ShippingProviderPricingMatrix.group_id.asc(),
                ShippingProviderPricingMatrix.min_kg.asc(),
                ShippingProviderPricingMatrix.max_kg.asc().nulls_last(),
                ShippingProviderPricingMatrix.id.asc(),
            )
            .all()
        )
        for row in matrix_rows:
            matrix_by_group.setdefault(row.group_id, []).append(row)

    destination_groups: List[DestinationGroupOut] = []
    for g in groups_raw:
        destination_groups.append(
            to_destination_group_out(
                g,
                members_by_group.get(g.id, []),
                matrix_by_group.get(g.id, []),
            )
        )

    surcharges_raw = (
        db.query(ShippingProviderSurcharge)
        .filter(ShippingProviderSurcharge.scheme_id == scheme_id)
        .order_by(ShippingProviderSurcharge.id.asc())
        .all()
    )
    surcharges: List[SurchargeOut] = [to_surcharge_out(s) for s in surcharges_raw]

    return sch, destination_groups, surcharges
