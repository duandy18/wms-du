# app/api/routers/pricing_integrity/helpers.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def list_province_members(db: Session, *, zone_id: int) -> list[str]:
    rows = (
        db.query(ShippingProviderZoneMember.value)
        .filter(
            ShippingProviderZoneMember.zone_id == zone_id,
            ShippingProviderZoneMember.level == "province",
        )
        .order_by(ShippingProviderZoneMember.value.asc())
        .all()
    )
    out: list[str] = []
    for (v,) in rows:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        out.append(s)
    return out


def count_province_members(db: Session, *, zone_id: int) -> int:
    return (
        db.query(ShippingProviderZoneMember.id)
        .filter(
            ShippingProviderZoneMember.zone_id == zone_id,
            ShippingProviderZoneMember.level == "province",
        )
        .count()
    )


def count_brackets(db: Session, *, zone_id: int) -> int:
    return db.query(ShippingProviderZoneBracket.id).filter(ShippingProviderZoneBracket.zone_id == zone_id).count()


def brackets_ranges_preview(db: Session, *, zone_id: int, limit: int = 8) -> list[str]:
    bs = (
        db.query(ShippingProviderZoneBracket)
        .filter(ShippingProviderZoneBracket.zone_id == zone_id)
        .order_by(
            ShippingProviderZoneBracket.min_kg.asc(),
            ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
            ShippingProviderZoneBracket.id.asc(),
        )
        .limit(limit)
        .all()
    )
    out: list[str] = []
    for b in bs:
        mn = str(getattr(b, "min_kg"))
        mx_raw = getattr(b, "max_kg", None)
        mx = "" if mx_raw is None else str(mx_raw)
        out.append(f"[{mn},{mx}]")
    return out
