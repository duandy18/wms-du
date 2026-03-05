# app/services/shipping_quote/surcharge_select.py
from __future__ import annotations

from typing import List

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .types import Dest


def extract_dest_scope_key(condition_json: dict) -> tuple[str, str, str | None] | None:
    """
    用于算价阶段的“同省 city 优先 / province 退让”。
    识别新结构（优先）与旧结构（列表长度=1）。

    返回：(scope, province, city?)
    """
    if not isinstance(condition_json, dict):
        return None
    dest = condition_json.get("dest")
    if not isinstance(dest, dict):
        return None

    scope = dest.get("scope")
    prov = dest.get("province")
    city = dest.get("city")

    # 新结构
    if isinstance(scope, str) and scope.strip().lower() in ("province", "city"):
        sc = scope.strip().lower()
        if not (isinstance(prov, str) and prov.strip()):
            return None
        pv = prov.strip()
        if sc == "province":
            return ("province", pv, None)
        if isinstance(city, str) and city.strip():
            return ("city", pv, city.strip())
        return None

    # 旧结构（列表长度=1）
    provs = dest.get("province")
    cities = dest.get("city")
    if isinstance(provs, list) and len(provs) == 1 and isinstance(provs[0], str) and provs[0].strip():
        pv = provs[0].strip()
        if isinstance(cities, list) and len(cities) == 1 and isinstance(cities[0], str) and cities[0].strip():
            return ("city", pv, cities[0].strip())
        if cities is None or (isinstance(cities, list) and len(cities) == 0):
            return ("province", pv, None)

    return None


def select_surcharges_city_wins(
    *,
    matched: List[ShippingProviderSurcharge],
    dest: Dest,
    reasons: List[str],
) -> List[ShippingProviderSurcharge]:
    """
    规则：
    - 允许叠加（flag_any 等不带 dest key 的规则全部保留）
    - 对 dest scope 规则：同省如果命中任何 city，则丢弃该省命中的 province
    - 同 key 重复：只取 id 最小的一个，其余记录 reason 并忽略
    """
    hit_city_provinces: set[str] = set()
    keyed: List[tuple[ShippingProviderSurcharge, tuple[str, str, str | None]]] = []
    unkeyed: List[ShippingProviderSurcharge] = []

    for s in matched:
        k = extract_dest_scope_key(s.condition_json or {})
        if not k:
            unkeyed.append(s)
            continue
        keyed.append((s, k))
        if k[0] == "city":
            hit_city_provinces.add(k[1])

    # 去重：同 key 取 id 最小的一个
    seen_key: dict[tuple[str, str, str | None], ShippingProviderSurcharge] = {}
    dup_ignored: List[ShippingProviderSurcharge] = []
    for s, k in keyed:
        prev = seen_key.get(k)
        if prev is None:
            seen_key[k] = s
            continue
        if int(s.id) < int(prev.id):
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
    final_surcharges.extend(unkeyed)
    final_surcharges.extend(sorted(chosen_keyed, key=lambda x: int(x.id)))
    return final_surcharges
