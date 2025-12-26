# app/api/routers/shipping_provider_pricing_schemes/schemas/__init__.py

from .common import WeightSegmentIn, ZoneMemberOut
from .bracket import ZoneBracketOut, ZoneBracketCreateIn, ZoneBracketUpdateIn
from .zone import ZoneOut, ZoneCreateIn, ZoneUpdateIn, ZoneCreateAtomicIn, ZoneMemberCreateIn
from .surcharge import SurchargeOut, SurchargeCreateIn, SurchargeUpdateIn
from .scheme import (
    SchemeOut,
    SchemeSegmentOut,
    SchemeListOut,
    SchemeDetailOut,
    SchemeCreateIn,
    SchemeUpdateIn,
)
from .segment_template import (
    SegmentTemplateOut,
    SegmentTemplateItemOut,
    SegmentTemplateItemIn,
    SegmentTemplateListOut,
    SegmentTemplateDetailOut,
    SegmentTemplateCreateIn,
    SegmentTemplateItemsPutIn,
    SegmentTemplateItemActivePatchIn,
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
]
