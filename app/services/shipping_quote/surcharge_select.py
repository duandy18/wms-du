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


def select_covering_surcharge(
    *,
    matched: List[ShippingProviderSurcharge],
    dest: Dest,
    reasons: List[str],
) -> ShippingProviderSurcharge | None:
    """
    覆盖型附加费选择：
    - city > province
    - 同层同命中如出现多条，先取 id 最小者，并记录 reason
    """
    _ = dest

    city_rows = [s for s in matched if str(getattr(s, "scope", "")).strip().lower() == "city"]
    if city_rows:
        city_rows = sorted(city_rows, key=lambda s: int(s.id))
        if len(city_rows) > 1:
            reasons.append("surcharge_conflict_same_scope: city scope duplicated, choose lowest id")
        return city_rows[0]

    province_rows = [s for s in matched if str(getattr(s, "scope", "")).strip().lower() == "province"]
    if province_rows:
        province_rows = sorted(province_rows, key=lambda s: int(s.id))
        if len(province_rows) > 1:
            reasons.append("surcharge_conflict_same_scope: province scope duplicated, choose lowest id")
        return province_rows[0]

    return None


def select_surcharges_city_wins(
    *,
    matched: List[ShippingProviderSurcharge],
    dest: Dest,
    reasons: List[str],
) -> List[ShippingProviderSurcharge]:
    """
    兼容旧调用方的包装：
    - 新语义改为“单命中覆盖型”
    - 返回 0 或 1 条
    """
    chosen = select_covering_surcharge(matched=matched, dest=dest, reasons=reasons)
    if chosen is None:
        return []
    return [chosen]
