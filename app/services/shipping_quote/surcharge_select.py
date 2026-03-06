# app/services/shipping_quote/surcharge_select.py
from __future__ import annotations

from typing import List

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .types import Dest


def _province_key(s: ShippingProviderSurcharge) -> str:
    return str(getattr(s, "province_code", None) or getattr(s, "province_name", None) or "").strip()


def _city_key(s: ShippingProviderSurcharge) -> str:
    return str(getattr(s, "city_code", None) or getattr(s, "city_name", None) or "").strip()


def extract_dest_scope_key(s: ShippingProviderSurcharge) -> tuple[str, str, str | None] | None:
    """
    结构化 key：
    - province -> (province, province_key, None)
    - city     -> (city, province_key, city_key)
    - always   -> None
    """
    scope = str(getattr(s, "scope", "") or "").strip().lower()
    if scope == "province":
        pk = _province_key(s)
        if not pk:
            return None
        return ("province", pk, None)

    if scope == "city":
        pk = _province_key(s)
        ck = _city_key(s)
        if not pk or not ck:
            return None
        return ("city", pk, ck)

    return None


def select_surcharges_city_wins(
    *,
    matched: List[ShippingProviderSurcharge],
    dest: Dest,
    reasons: List[str],
) -> List[ShippingProviderSurcharge]:
    """
    规则：
    - always 保留
    - 同省 city 命中时，province 被抑制
    - 同 key 重复时，priority 小者优先，再按 id 小者优先
    """
    _ = dest  # 当前无需直接读取，保留签名

    hit_city_provinces: set[str] = set()
    keyed: List[tuple[ShippingProviderSurcharge, tuple[str, str, str | None]]] = []
    unkeyed: List[ShippingProviderSurcharge] = []

    for s in matched:
        k = extract_dest_scope_key(s)
        if not k:
            unkeyed.append(s)
            continue
        keyed.append((s, k))
        if k[0] == "city":
            hit_city_provinces.add(k[1])

    seen_key: dict[tuple[str, str, str | None], ShippingProviderSurcharge] = {}
    dup_ignored: List[ShippingProviderSurcharge] = []

    for s, k in keyed:
        prev = seen_key.get(k)
        if prev is None:
            seen_key[k] = s
            continue

        s_pri = int(getattr(s, "priority", 100) or 100)
        p_pri = int(getattr(prev, "priority", 100) or 100)

        if (s_pri, int(s.id)) < (p_pri, int(prev.id)):
            dup_ignored.append(prev)
            seen_key[k] = s
        else:
            dup_ignored.append(s)

    for s in dup_ignored:
        reasons.append(f"surcharge_ignored_duplicate_key: id={s.id} name={s.name}")

    for prov in sorted(list(hit_city_provinces)):
        reasons.append(f"surcharge_dest_mode: province={prov} (city wins, province suppressed)")

    chosen_keyed: List[ShippingProviderSurcharge] = []
    for k, s in seen_key.items():
        scope2, prov2, _city2 = k
        if scope2 == "province" and prov2 in hit_city_provinces:
            continue
        chosen_keyed.append(s)

    final_surcharges: List[ShippingProviderSurcharge] = []
    final_surcharges.extend(sorted(unkeyed, key=lambda x: (int(getattr(x, "priority", 100) or 100), int(x.id))))
    final_surcharges.extend(sorted(chosen_keyed, key=lambda x: (int(getattr(x, "priority", 100) or 100), int(x.id))))
    return final_surcharges
