# app/tms/quote/matchers.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .context import (
    QuoteGroupContext,
    QuoteGroupMemberContext,
    QuoteMatrixRowContext,
)
from .types import Dest, _s


def _match_destination_group(
    groups: List[QuoteGroupContext],
    members: List[QuoteGroupMemberContext],
    dest: Dest,
) -> Tuple[Optional[QuoteGroupContext], Optional[QuoteGroupMemberContext]]:
    """
    Level-3 基本费目的地组匹配（province-only）：
    1) 优先匹配有 province members 命中的 active group
    2) 若都不命中，则回退到 members 为空的 active group
    """
    dp_name = _s(dest.province)
    dp_code = _s(dest.province_code)

    by_group: Dict[int, List[QuoteGroupMemberContext]] = {}
    for m in members:
        by_group.setdefault(int(m.group_id), []).append(m)

    def member_hit(m: QuoteGroupMemberContext) -> bool:
        row_prov_code = _s(m.province_code)
        row_prov_name = _s(m.province_name)

        if row_prov_code and dp_code:
            return row_prov_code == dp_code
        return bool(row_prov_name and dp_name and row_prov_name == dp_name)

    groups_sorted = sorted(groups, key=lambda g: int(g.id))

    for g in groups_sorted:
        if not bool(g.active):
            continue
        ms = by_group.get(int(g.id), [])
        if not ms:
            continue
        for m in ms:
            if member_hit(m):
                return g, m

    for g in groups_sorted:
        if not bool(g.active):
            continue
        ms = by_group.get(int(g.id), [])
        if ms:
            continue
        return g, None

    return None, None


def _match_pricing_matrix(
    rows: List[QuoteMatrixRowContext],
    billable_weight_kg: float,
) -> Optional[QuoteMatrixRowContext]:
    """
    Level-3 命中语义（统一后终态）：
    左闭右开 [min_kg, max_kg)

    - 与数据库 exclusion constraint 的 [) 保持一致
    - 若有重叠，选择 min_kg 最大（更具体）的一条
    """
    w = float(billable_weight_kg)
    eps = 1e-9

    candidates: List[QuoteMatrixRowContext] = []
    for r in rows:
        if not bool(r.active):
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

    candidates.sort(key=lambda r: (float(r.min_kg), int(r.id)), reverse=True)
    return candidates[0]
