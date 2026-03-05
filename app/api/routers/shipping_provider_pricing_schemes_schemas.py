# app/api/routers/shipping_provider_pricing_schemes_schemas.py
from __future__ import annotations

# ============================================================
# DEPRECATED COMPAT LAYER (DO NOT USE IN NEW CODE)
# ------------------------------------------------------------
# ✅ 唯一事实出口已收敛为：
#   app.api.routers.shipping_provider_pricing_schemes.schemas
#
# 本文件仅为“历史兼容层”，原则上不应再被任何模块引用。
# 为避免新债引入漂移，可通过环境变量开启硬失败：
#
#   WMS_STRICT_SCHEMA_EXPORTS=1
#
# 开启后：一旦有代码 import 本文件，将直接抛错，逼迫使用新出口。
# ============================================================

import os

if os.getenv("WMS_STRICT_SCHEMA_EXPORTS", "").strip() in ("1", "true", "yes", "on"):
    raise RuntimeError(
        "Deprecated import: app.api.routers.shipping_provider_pricing_schemes_schemas. "
        "Use: app.api.routers.shipping_provider_pricing_schemes.schemas"
    )

from app.api.routers.shipping_provider_pricing_schemes.schemas import (  # noqa: F401
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
    # dest adjustment (structured destination facts)
    DestAdjustmentOut,
    DestAdjustmentUpsertIn,
    DestAdjustmentUpdateIn,
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
    # zone brackets matrix
    ZoneBracketsMatrixOut,
    ZoneBracketsMatrixGroupOut,
    SegmentRangeOut,
)

from app.api.routers.shipping_provider_pricing_schemes.validators import (  # noqa: F401
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
    # dest adjustment
    "DestAdjustmentOut",
    "DestAdjustmentUpsertIn",
    "DestAdjustmentUpdateIn",
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
    # zone brackets matrix
    "ZoneBracketsMatrixOut",
    "ZoneBracketsMatrixGroupOut",
    "SegmentRangeOut",
    # validators
    "validate_default_pricing_mode",
]
