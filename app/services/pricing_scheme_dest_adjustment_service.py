# app/services/pricing_scheme_dest_adjustment_service.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def _norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def _norm_required(s: Optional[str], field: str) -> str:
    s2 = _norm(s)
    if not s2:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    return s2


def _validate_scope(scope: Optional[str]) -> str:
    s = _norm_required(scope, "scope").lower()
    if s not in ("province", "city"):
        raise HTTPException(status_code=422, detail="scope must be 'province' or 'city'")
    return s


def _validate_amount(amount: object) -> Decimal:
    try:
        d = Decimal(str(amount))
    except Exception as e:
        raise HTTPException(status_code=422, detail="amount must be a number") from e
    if d.is_nan():
        raise HTTPException(status_code=422, detail="amount must be a number")
    if d < Decimal("0"):
        raise HTTPException(status_code=422, detail="amount must be >= 0")
    return d.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class DestAdjConflict:
    id: int
    scope: str
    province: str
    city: Optional[str]
    active: bool


def _to_conflict_row(x: PricingSchemeDestAdjustment) -> DestAdjConflict:
    return DestAdjConflict(
        id=int(x.id),
        scope=str(x.scope),
        province=str(x.province),
        city=str(x.city) if x.city is not None else None,
        active=bool(x.active),
    )


def ensure_dest_adjustment_mutual_exclusion(
    db: Session,
    *,
    scheme_id: int,
    target_scope: str,
    province: str,
    target_id: Optional[int],
    active: bool,
) -> None:
    """
    ✅ 硬约束：同一 scheme + 同一 province：
      - province 与 任意 city 不允许同时 active
    仅在 active=True 时触发（停用不需要检查）。
    """
    if not active:
        return

    province2 = _norm_required(province, "province")
    scope2 = _validate_scope(target_scope)

    opposite = "city" if scope2 == "province" else "province"

    q = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(scheme_id))
        .filter(PricingSchemeDestAdjustment.province == province2)
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
                "province": province2,
                "target_scope": scope2,
                "conflicts": [c.__dict__ for c in conflicts],
            },
        )


def upsert_dest_adjustment(
    db: Session,
    *,
    scheme_id: int,
    scope: str,
    province: str,
    city: Optional[str],
    amount: object,
    active: bool,
    priority: Optional[int] = None,
) -> PricingSchemeDestAdjustment:
    """
    ✅ 事实写入点（幂等）：
      - key: (scheme_id, scope, province, city)
      - 同 key：update；否则 create
      - 激活时：必须过互斥门禁
    """
    sch = db.get(ShippingProviderPricingScheme, int(scheme_id))
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    scope2 = _validate_scope(scope)
    province2 = _norm_required(province, "province")
    city2 = _norm(city)

    if scope2 == "province":
        city2 = None
    else:
        if not city2:
            raise HTTPException(status_code=422, detail="city is required when scope='city'")

    amt = _validate_amount(amount)
    pri = int(priority) if priority is not None else 100

    # 幂等 key 查找
    target: PricingSchemeDestAdjustment | None = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(scheme_id))
        .filter(PricingSchemeDestAdjustment.scope == scope2)
        .filter(PricingSchemeDestAdjustment.province == province2)
        .filter(
            PricingSchemeDestAdjustment.city.is_(city2)
            if city2 is None
            else PricingSchemeDestAdjustment.city == city2
        )
        .one_or_none()
    )

    if target is None:
        ensure_dest_adjustment_mutual_exclusion(
            db,
            scheme_id=int(scheme_id),
            target_scope=scope2,
            province=province2,
            target_id=None,
            active=bool(active),
        )
        target = PricingSchemeDestAdjustment(
            scheme_id=int(scheme_id),
            scope=scope2,
            province=province2,
            city=city2,
            amount=float(amt),
            active=bool(active),
            priority=pri,
        )
        db.add(target)
        db.commit()
        db.refresh(target)
        return target

    ensure_dest_adjustment_mutual_exclusion(
        db,
        scheme_id=int(scheme_id),
        target_scope=scope2,
        province=province2,
        target_id=int(target.id),
        active=bool(active),
    )

    target.scope = scope2
    target.province = province2
    target.city = city2
    target.amount = float(amt)
    target.active = bool(active)
    target.priority = pri

    db.commit()
    db.refresh(target)
    return target


def update_dest_adjustment(
    db: Session,
    *,
    dest_adjustment_id: int,
    scope: Optional[str] = None,
    province: Optional[str] = None,
    city: Optional[str] = None,
    amount: Optional[object] = None,
    active: Optional[bool] = None,
    priority: Optional[int] = None,
) -> PricingSchemeDestAdjustment:
    """
    ✅ patch 入口：
      - 常用：改 amount/active/priority
      - 允许改 scope/province/city，但会做去重与互斥检查
    """
    row = db.get(PricingSchemeDestAdjustment, int(dest_adjustment_id))
    if not row:
        raise HTTPException(status_code=404, detail="Dest adjustment not found")

    next_scope = _validate_scope(scope) if scope is not None else str(row.scope)
    next_prov = _norm_required(province, "province") if province is not None else str(row.province)
    next_city = _norm(city) if city is not None else (str(row.city) if row.city is not None else None)

    if next_scope == "province":
        next_city = None
    else:
        if not next_city:
            raise HTTPException(status_code=422, detail="city is required when scope='city'")

    next_amt = _validate_amount(amount) if amount is not None else _validate_amount(row.amount)
    next_active = bool(active) if active is not None else bool(row.active)
    next_pri = int(priority) if priority is not None else int(row.priority or 100)

    dup = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(row.scheme_id))
        .filter(PricingSchemeDestAdjustment.scope == next_scope)
        .filter(PricingSchemeDestAdjustment.province == next_prov)
        .filter(
            PricingSchemeDestAdjustment.city.is_(next_city)
            if next_city is None
            else PricingSchemeDestAdjustment.city == next_city
        )
        .filter(PricingSchemeDestAdjustment.id != int(row.id))
        .one_or_none()
    )
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "dest_adjustment_duplicate_key",
                "message": "duplicate dest adjustment key under same scheme",
                "duplicate_id": int(dup.id),
            },
        )

    ensure_dest_adjustment_mutual_exclusion(
        db,
        scheme_id=int(row.scheme_id),
        target_scope=next_scope,
        province=next_prov,
        target_id=int(row.id),
        active=next_active,
    )

    row.scope = next_scope
    row.province = next_prov
    row.city = next_city
    row.amount = float(next_amt)
    row.active = next_active
    row.priority = next_pri

    db.commit()
    db.refresh(row)
    return row


def delete_dest_adjustment(db: Session, *, dest_adjustment_id: int) -> None:
    """
    ✅ delete 硬约束：启用态不可删除，必须先停用
    """
    row = db.get(PricingSchemeDestAdjustment, int(dest_adjustment_id))
    if not row:
        raise HTTPException(status_code=404, detail="Dest adjustment not found")

    if bool(row.active):
        raise HTTPException(status_code=409, detail="must disable dest adjustment before delete")

    db.delete(row)
    db.commit()
