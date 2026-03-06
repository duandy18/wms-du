# app/services/shipping_quote/matchers.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember

from .types import Dest, _s


def _match_zone(
    zones: List[ShippingProviderZone],
    members: List[ShippingProviderZoneMember],
    dest: Dest,
) -> Tuple[Optional[ShippingProviderZone], Optional[ShippingProviderZoneMember]]:
    """
    生产级 Zone 匹配（legacy）：

    1) 优先匹配“有 members 命中”的 zone（按 zone.id asc 稳定）
    2) 若全部不命中，则允许回退到“兜底 zone”：
       - zone.active=true
       - 且该 zone 下 members 为空（明确语义：默认覆盖）
       - 仍按 zone.id asc 选择最优兜底
    """
    dp = _s(dest.province)
    dc = _s(dest.city)
    dd = _s(dest.district)

    by_zone: Dict[int, List[ShippingProviderZoneMember]] = {}
    for m in members:
        by_zone.setdefault(m.zone_id, []).append(m)

    def member_hit(m: ShippingProviderZoneMember) -> bool:
        lvl = (m.level or "").lower()
        val = (m.value or "").strip()
        if not val:
            return False

        if lvl == "province":
            return dp == val
        if lvl == "city":
            return dc == val
        if lvl == "district":
            return dd == val
        if lvl == "text":
            hay = " ".join([x for x in [dp, dc, dd] if x])
            return (val in hay) or (hay in val) or (val == hay)
        return False

    zones_sorted = sorted(zones, key=lambda z: int(z.id))

    for z in zones_sorted:
        if not z.active:
            continue
        ms = by_zone.get(z.id, [])
        if not ms:
            continue
        for m in ms:
            if member_hit(m):
                return z, m

    for z in zones_sorted:
        if not z.active:
            continue
        ms = by_zone.get(z.id, [])
        if ms:
            continue
        return z, None

    return None, None


def _match_bracket(
    brackets: List[ShippingProviderZoneBracket],
    billable_weight_kg: float,
) -> Optional[ShippingProviderZoneBracket]:
    """
    legacy 命中语义：左开右闭 (min_kg, max_kg]
    - max_kg 为 NULL 视为 infinity
    - 若有重叠，选择 min_kg 最大（更具体）的一条
    """
    w = float(billable_weight_kg)
    eps = 1e-9

    candidates: List[ShippingProviderZoneBracket] = []
    for b in brackets:
        if not b.active:
            continue

        mn = float(b.min_kg)
        mx = float(b.max_kg) if b.max_kg is not None else None

        if w <= mn + eps:
            continue
        if mx is not None and w > mx + eps:
            continue

        candidates.append(b)

    if not candidates:
        return None

    candidates.sort(key=lambda b: (float(b.min_kg), b.id), reverse=True)
    return candidates[0]


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
    Phase C 双轨验证口径：

    这里故意沿用 legacy 的左开右闭 (min_kg, max_kg]，
    先保证 level3 与 legacy 可直接对比。
    真正切主链时，再统一到最终区间合同。
    """
    w = float(billable_weight_kg)
    eps = 1e-9

    candidates: List[ShippingProviderPricingMatrix] = []
    for r in rows:
        if not r.active:
            continue

        mn = float(r.min_kg)
        mx = float(r.max_kg) if r.max_kg is not None else None

        if w <= mn + eps:
            continue
        if mx is not None and w > mx + eps:
            continue

        candidates.append(r)

    if not candidates:
        return None

    candidates.sort(key=lambda r: (float(r.min_kg), r.id), reverse=True)
    return candidates[0]
