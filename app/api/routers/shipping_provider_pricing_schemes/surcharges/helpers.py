# app/api/routers/shipping_provider_pricing_schemes/surcharges/helpers.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


_ALLOWED_SCOPE = {"always", "province", "city"}


def normalize_scope(v: str) -> str:
    t = (v or "").strip().lower()
    if t not in _ALLOWED_SCOPE:
        raise HTTPException(status_code=422, detail="scope must be one of: always / province / city")
    return t


def _norm(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _same_province(
    row: ShippingProviderSurcharge,
    *,
    province_code: str | None,
    province_name: str | None,
) -> bool:
    row_code = _norm(getattr(row, "province_code", None))
    row_name = _norm(getattr(row, "province_name", None))
    target_code = _norm(province_code)
    target_name = _norm(province_name)

    if row_code and target_code:
        return row_code == target_code
    if row_name and target_name:
        return row_name == target_name
    return False


def ensure_dest_mutual_exclusion(
    db: Session,
    *,
    scheme_id: int,
    target_scope: str,
    province_code: str | None,
    province_name: str | None,
    target_id: int | None,
    active: bool,
) -> None:
    """
    硬约束：
    - 同一省份下，province 与 city 规则不能同时 active
    """
    if not active:
        return

    scope2 = normalize_scope(target_scope)
    if scope2 not in ("province", "city"):
        return

    q = (
        db.query(ShippingProviderSurcharge)
        .filter(
            ShippingProviderSurcharge.scheme_id == int(scheme_id),
            ShippingProviderSurcharge.active.is_(True),
            ShippingProviderSurcharge.scope.in_(("province", "city")),
        )
        .order_by(ShippingProviderSurcharge.id.asc())
    )
    if target_id is not None:
        q = q.filter(ShippingProviderSurcharge.id != int(target_id))

    rows = q.all()
    for s in rows:
        if not _same_province(s, province_code=province_code, province_name=province_name):
            continue
        if scope2 == "province" and str(s.scope) == "city":
            raise HTTPException(
                status_code=409,
                detail=f"conflict: province surcharge cannot be active when city surcharges exist for province={province_name or province_code}",
            )
        if scope2 == "city" and str(s.scope) == "province":
            raise HTTPException(
                status_code=409,
                detail=f"conflict: city surcharge cannot be active when province surcharge exists for province={province_name or province_code}",
            )
