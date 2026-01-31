# app/services/pricing_scheme_dest_adjustments/conflicts.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from .validators import norm_required, validate_scope


@dataclass(frozen=True)
class DestAdjConflict:
    id: int
    scope: str
    province_code: str
    city_code: Optional[str]
    province_name: Optional[str]
    city_name: Optional[str]
    active: bool


def _to_conflict_row(x: PricingSchemeDestAdjustment) -> DestAdjConflict:
    return DestAdjConflict(
        id=int(x.id),
        scope=str(x.scope),
        province_code=str(x.province_code),
        city_code=str(x.city_code) if x.city_code is not None else None,
        province_name=str(x.province_name) if x.province_name is not None else None,
        city_name=str(x.city_name) if x.city_name is not None else None,
        active=bool(x.active),
    )


def ensure_dest_adjustment_mutual_exclusion(
    db: Session,
    *,
    scheme_id: int,
    target_scope: str,
    province_code: str,
    target_id: Optional[int],
    active: bool,
) -> None:
    """
    ✅ 硬约束（事实口径：province_code）：
    同一 scheme + 同一 province_code：
      - province 与 任意 city 不允许同时 active
    仅在 active=True 时触发（停用不需要检查）。
    """
    if not active:
        return

    scope2 = validate_scope(target_scope)
    prov_code2 = norm_required(province_code, "province_code")

    opposite = "city" if scope2 == "province" else "province"

    q = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(scheme_id))
        .filter(PricingSchemeDestAdjustment.province_code == prov_code2)
        .filter(PricingSchemeDestAdjustment.scope == opposite)
        .filter(PricingSchemeDestAdjustment.active.is_(True))
        .order_by(PricingSchemeDestAdjustment.id.asc())
    )
    if target_id is not None:
        q = q.filter(PricingSchemeDestAdjustment.id != int(target_id))

    rows = q.all()
    if rows:
        conflicts = [_to_conflict_row(r) for r in rows]
        raise HTTPException(
            status_code=409,
            detail={
                "code": "dest_adjustment_mutual_exclusion_conflict",
                "message": "conflict: province vs city adjustments cannot be active together in same province",
                "scheme_id": int(scheme_id),
                "province_code": prov_code2,
                "target_scope": scope2,
                "conflicts": [c.__dict__ for c in conflicts],
            },
        )
