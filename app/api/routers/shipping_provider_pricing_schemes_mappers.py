# app/api/routers/shipping_provider_pricing_schemes_mappers.py
from __future__ import annotations

from typing import List

from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SchemeOut,
    SchemeSegmentOut,
    SurchargeOut,
    ZoneBracketOut,
    ZoneMemberOut,
    ZoneOut,
)
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def to_member_out(m: ShippingProviderZoneMember) -> ZoneMemberOut:
    return ZoneMemberOut(id=m.id, zone_id=m.zone_id, level=m.level, value=m.value)


def to_bracket_out(b: ShippingProviderZoneBracket) -> ZoneBracketOut:
    # base_kg 可能还在迁移途中：用 getattr 兼容一下，避免旧环境炸
    base_kg = getattr(b, "base_kg", None)
    return ZoneBracketOut(
        id=b.id,
        zone_id=b.zone_id,
        min_kg=b.min_kg,
        max_kg=b.max_kg,
        pricing_mode=b.pricing_mode,
        flat_amount=b.flat_amount,
        base_amount=b.base_amount,
        rate_per_kg=b.rate_per_kg,
        base_kg=base_kg,
        price_json=b.price_json or {},
        active=bool(b.active),
    )


def to_zone_out(
    z: ShippingProviderZone,
    members: List[ShippingProviderZoneMember],
    brackets: List[ShippingProviderZoneBracket],
) -> ZoneOut:
    return ZoneOut(
        id=z.id,
        scheme_id=z.scheme_id,
        name=z.name,
        active=bool(z.active),
        members=[to_member_out(x) for x in members],
        brackets=[to_bracket_out(x) for x in brackets],
    )


def to_surcharge_out(s: ShippingProviderSurcharge) -> SurchargeOut:
    return SurchargeOut(
        id=s.id,
        scheme_id=s.scheme_id,
        name=s.name,
        active=bool(s.active),
        condition_json=s.condition_json or {},
        amount_json=s.amount_json or {},
    )


def to_scheme_segment_out(seg: ShippingProviderPricingSchemeSegment) -> SchemeSegmentOut:
    return SchemeSegmentOut(
        id=seg.id,
        scheme_id=seg.scheme_id,
        ord=seg.ord,
        min_kg=seg.min_kg,
        max_kg=seg.max_kg,
        active=bool(seg.active),
    )


def _must_get_shipping_provider_name(sch: ShippingProviderPricingScheme) -> str:
    """
    ✅ Phase 6：刚性契约
    - SchemeOut.shipping_provider_name 必须由后端提供
    - 不允许前端推导/猜测
    - 若 ORM 关系未加载或数据异常，直接抛错（让契约早爆）
    """
    sp = getattr(sch, "shipping_provider", None)
    name = getattr(sp, "name", None) if sp is not None else None
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(
            f"ShippingProvider name is required for scheme_id={sch.id} shipping_provider_id={sch.shipping_provider_id}"
        )
    return name.strip()


def to_scheme_out(
    sch: ShippingProviderPricingScheme,
    zones: List[ZoneOut],
    surcharges: List[SurchargeOut],
) -> SchemeOut:
    # default_pricing_mode 已落库：若旧库/旧环境暂时缺列，用 getattr 兜底
    dpm = getattr(sch, "default_pricing_mode", "linear_total")

    segs = getattr(sch, "segments", None) or []

    return SchemeOut(
        id=sch.id,
        shipping_provider_id=sch.shipping_provider_id,
        shipping_provider_name=_must_get_shipping_provider_name(sch),
        name=sch.name,
        active=bool(sch.active),
        currency=sch.currency,
        effective_from=sch.effective_from,
        effective_to=sch.effective_to,
        default_pricing_mode=dpm,
        billable_weight_rule=sch.billable_weight_rule,
        # ✅ 归档字段：DB 非空但输出 null 的根因就在这里（之前漏映射）
        archived_at=getattr(sch, "archived_at", None),
        segments_json=getattr(sch, "segments_json", None),
        segments_updated_at=getattr(sch, "segments_updated_at", None),
        segments=[to_scheme_segment_out(x) for x in segs],
        zones=zones,
        surcharges=surcharges,
    )
