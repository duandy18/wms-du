# app/api/routers/shipping_provider_pricing_schemes_schemas.py
from __future__ import annotations

from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    # common
    WeightSegmentIn,
    ZoneMemberOut,
    # bracket
    ZoneBracketOut,
    ZoneBracketCreateIn,
    ZoneBracketUpdateIn,
    # zone
    ZoneOut,
    ZoneCreateIn,
    ZoneUpdateIn,
    ZoneCreateAtomicIn,
    ZoneMemberCreateIn,
    ZoneProvinceMembersReplaceIn,
    # surcharge
    SurchargeOut,
    SurchargeCreateIn,
    SurchargeUpdateIn,
    # scheme
    SchemeOut,
    SchemeSegmentOut,
    SchemeListOut,
    SchemeDetailOut,
    SchemeCreateIn,
    SchemeUpdateIn,
    # segment templates
    SegmentTemplateOut,
    SegmentTemplateItemOut,
    SegmentTemplateItemIn,
    SegmentTemplateListOut,
    SegmentTemplateDetailOut,
    SegmentTemplateCreateIn,
    SegmentTemplateItemsPutIn,
    SegmentTemplateItemActivePatchIn,
)

from app.api.routers.shipping_provider_pricing_schemes.validators import (
    validate_default_pricing_mode,
)

__all__ = [
    # common
    "WeightSegmentIn",
    "ZoneMemberOut",
    # bracket
    "ZoneBracketOut",
    "ZoneBracketCreateIn",
    "ZoneBracketUpdateIn",
    # zone
    "ZoneOut",
    "ZoneCreateIn",
    "ZoneUpdateIn",
    "ZoneCreateAtomicIn",
    "ZoneMemberCreateIn",
    "ZoneProvinceMembersReplaceIn",
    # surcharge
    "SurchargeOut",
    "SurchargeCreateIn",
    "SurchargeUpdateIn",
    # scheme
    "SchemeOut",
    "SchemeSegmentOut",
    "SchemeListOut",
    "SchemeDetailOut",
    "SchemeCreateIn",
    "SchemeUpdateIn",
    # segment templates
    "SegmentTemplateOut",
    "SegmentTemplateItemOut",
    "SegmentTemplateItemIn",
    "SegmentTemplateListOut",
    "SegmentTemplateDetailOut",
    "SegmentTemplateCreateIn",
    "SegmentTemplateItemsPutIn",
    "SegmentTemplateItemActivePatchIn",
    # validators
    "validate_default_pricing_mode",
]
