# app/services/shipping_quote/matchers.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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
    生产级 Zone 匹配（Phase 4 过渡裁决）：

    1) 优先匹配“有 members 命中”的 zone（按 zone.id asc 稳定）
    2) 若全部不命中，则允许回退到“兜底 zone”：
       - zone.active=true
       - 且该 zone 下 members 为空（明确语义：默认覆盖）
       - 仍按 zone.id asc 选择最优兜底

    返回 (zone, hit_member)。命中兜底时 hit_member=None，供 reasons 解释。
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

    # 1) 先找“有 member 命中”的 zone
    for z in zones_sorted:
        if not z.active:
            continue
        ms = by_zone.get(z.id, [])
        if not ms:
            continue
        for m in ms:
            if member_hit(m):
                return z, m

    # 2) 再找“兜底 zone”（members 为空）
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
    ✅ Phase 4+ 统一口径：左开右闭 (min_kg, max_kg]
    - max_kg 为 NULL 视为 infinity
    - 若有重叠，选择 min_kg 最大（更具体）的一条。

    注意：这是“命中语义”的铁律。前端/数据清洗必须与此一致。
    """
    w = float(billable_weight_kg)

    # 数值稳定性：避免浮点误差把边界判错
    eps = 1e-9

    candidates: List[ShippingProviderZoneBracket] = []
    for b in brackets:
        if not b.active:
            continue

        mn = float(b.min_kg)
        mx = float(b.max_kg) if b.max_kg is not None else None

        # 左开：w 必须严格大于 min
        if w <= mn + eps:
            continue

        # 右闭：w <= max（max None => ∞）
        if mx is not None and w > mx + eps:
            continue

        candidates.append(b)

    if not candidates:
        return None

    candidates.sort(key=lambda b: (float(b.min_kg), b.id), reverse=True)
    return candidates[0]
