from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.api.routers.shipping_provider_pricing_schemes_utils import segments_norm_to_rows
from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket


def replace_segments_table(db: Session, scheme_id: int, segs_norm: Optional[list]) -> None:
    """
    将 segs_norm（normalize_segments_json 的输出）落到段表：
    - v1：delete + insert（最稳、最简单）
    - active 默认 true（暂停由专门 endpoint 管）
    """
    db.query(ShippingProviderPricingSchemeSegment).filter(
        ShippingProviderPricingSchemeSegment.scheme_id == scheme_id
    ).delete(synchronize_session=False)

    if not segs_norm:
        return

    rows = segments_norm_to_rows(segs_norm)
    for ord_i, mn, mx in rows:
        db.add(
            ShippingProviderPricingSchemeSegment(
                scheme_id=scheme_id,
                ord=int(ord_i),
                min_kg=mn,
                max_kg=mx,
                active=True,
            )
        )


def scheme_has_any_brackets(db: Session, scheme_id: int) -> bool:
    hit = (
        db.query(ShippingProviderZoneBracket.id)
        .join(ShippingProviderZone, ShippingProviderZone.id == ShippingProviderZoneBracket.zone_id)
        .filter(ShippingProviderZone.scheme_id == scheme_id)
        .limit(1)
        .first()
    )
    return bool(hit)
