# app/services/shipping_quote/matchers.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix

from .types import Dest, _s


def _match_destination_group(
    groups: List[ShippingProviderDestinationGroup],
    members: List[ShippingProviderDestinationGroupMember],
    dest: Dest,
) -> Tuple[Optional[ShippingProviderDestinationGroup], Optional[ShippingProviderDestinationGroupMember]]:
    """
    Level-3 目的地收费组匹配：
    1) 优先匹配有 members 命中的 group
    2) 若都不命中，则回退到 members 为空的 active group
    """
    dp_name = _s(dest.province)
    dc_name = _s(dest.city)
    dp_code = _s(dest.province_code)
    dc_code = _s(dest.city_code)

    by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
    for m in members:
        by_group.setdefault(m.group_id, []).append(m)

    def member_hit(m: ShippingProviderDestinationGroupMember) -> bool:
        scope = (m.scope or "").strip().lower()

        row_prov_code = _s(m.province_code)
        row_city_code = _s(m.city_code)
        row_prov_name = _s(m.province_name)
        row_city_name = _s(m.city_name)

        if scope == "province":
            if row_prov_code and dp_code:
                return row_prov_code == dp_code
            return bool(row_prov_name and dp_name and row_prov_name == dp_name)

        if scope == "city":
            province_ok = False
            if row_prov_code and dp_code:
                province_ok = row_prov_code == dp_code
            elif row_prov_name and dp_name:
                province_ok = row_prov_name == dp_name

            if not province_ok:
                return False

            if row_city_code and dc_code:
                return row_city_code == dc_code
            return bool(row_city_name and dc_name and row_city_name == dc_name)

        return False

    groups_sorted = sorted(groups, key=lambda g: int(g.id))

    for g in groups_sorted:
        if not g.active:
            continue
        ms = by_group.get(g.id, [])
        if not ms:
            continue
        for m in ms:
            if member_hit(m):
                return g, m

    for g in groups_sorted:
        if not g.active:
            continue
        ms = by_group.get(g.id, [])
        if ms:
            continue
        return g, None

    return None, None


def _match_pricing_matrix(
    rows: List[ShippingProviderPricingMatrix],
    billable_weight_kg: float,
) -> Optional[ShippingProviderPricingMatrix]:
    """
    Level-3 命中语义（统一后终态）：
    左闭右开 [min_kg, max_kg)

    - 与数据库 exclusion constraint 的 [) 保持一致
    - 若有重叠，选择 min_kg 最大（更具体）的一条
    """
    w = float(billable_weight_kg)
    eps = 1e-9

    candidates: List[ShippingProviderPricingMatrix] = []
    for r in rows:
        if not r.active:
            continue

        mn = float(r.min_kg)
        mx = float(r.max_kg) if r.max_kg is not None else None

        if w < mn - eps:
            continue

        if mx is not None and w >= mx - eps:
            continue

        candidates.append(r)

    if not candidates:
        return None

    candidates.sort(key=lambda r: (float(r.min_kg), r.id), reverse=True)
    return candidates[0]
