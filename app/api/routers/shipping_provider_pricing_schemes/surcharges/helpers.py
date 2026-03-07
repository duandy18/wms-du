# app/api/routers/shipping_provider_pricing_schemes/surcharges/helpers.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


_ALLOWED_SCOPE = {"province", "city"}


def normalize_scope(v: str) -> str:
    t = (v or "").strip().lower()
    if t not in _ALLOWED_SCOPE:
        raise HTTPException(status_code=422, detail="scope must be one of: province / city")
    return t


def _norm(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def province_identity_key(*, province_code: str | None, province_name: str | None) -> tuple[str, str]:
    return (_norm(province_code), _norm(province_name))


def city_identity_key(
    *,
    province_code: str | None,
    province_name: str | None,
    city_code: str | None,
    city_name: str | None,
) -> tuple[str, str, str, str]:
    return (
        _norm(province_code),
        _norm(province_name),
        _norm(city_code),
        _norm(city_name),
    )


def surcharge_scope_key(
    *,
    scope: str,
    province_code: str | None,
    province_name: str | None,
    city_code: str | None,
    city_name: str | None,
) -> tuple[str, tuple[str, ...]]:
    scope2 = normalize_scope(scope)
    if scope2 == "province":
        return ("province", province_identity_key(province_code=province_code, province_name=province_name))
    return (
        "city",
        city_identity_key(
            province_code=province_code,
            province_name=province_name,
            city_code=city_code,
            city_name=city_name,
        ),
    )


def row_scope_key(row: ShippingProviderSurcharge) -> tuple[str, tuple[str, ...]]:
    return surcharge_scope_key(
        scope=str(getattr(row, "scope", "")),
        province_code=getattr(row, "province_code", None),
        province_name=getattr(row, "province_name", None),
        city_code=getattr(row, "city_code", None),
        city_name=getattr(row, "city_name", None),
    )


def _same_province(
    row: ShippingProviderSurcharge,
    *,
    province_code: str | None,
    province_name: str | None,
) -> bool:
    row_code, row_name = province_identity_key(
        province_code=getattr(row, "province_code", None),
        province_name=getattr(row, "province_name", None),
    )
    target_code, target_name = province_identity_key(
        province_code=province_code,
        province_name=province_name,
    )

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
    - surcharge 只支持 province / city
    - 同一省份下，province 与 city 规则不能同时 active
    """
    if not active:
        return

    scope2 = normalize_scope(target_scope)

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
                detail=(
                    "conflict: province surcharge cannot be active when city surcharges exist "
                    f"for province={province_name or province_code}"
                ),
            )
        if scope2 == "city" and str(s.scope) == "province":
            raise HTTPException(
                status_code=409,
                detail=(
                    "conflict: city surcharge cannot be active when province surcharge exists "
                    f"for province={province_name or province_code}"
                ),
            )


def handle_surcharge_integrity_error(e: IntegrityError) -> None:
    msg = ""
    try:
        msg = (str(getattr(e, "orig", "") or "")).lower()
    except Exception:
        msg = str(e).lower()

    if "uq_sp_surcharges_scheme_name" in msg:
        raise HTTPException(status_code=409, detail="Surcharge name already exists in this scheme")

    if "uq_sp_surcharges_active_province_key" in msg:
        raise HTTPException(
            status_code=409,
            detail="Active province surcharge already exists for this scheme/province",
        )

    if "uq_sp_surcharges_active_city_key" in msg:
        raise HTTPException(
            status_code=409,
            detail="Active city surcharge already exists for this scheme/province/city",
        )

    if "ck_sp_surcharges_scope_valid" in msg:
        raise HTTPException(status_code=422, detail="scope must be one of: province / city")

    if "ck_sp_surcharges_scope_fields" in msg:
        raise HTTPException(
            status_code=422,
            detail="Invalid surcharge scope fields for province/city rule",
        )

    if "ck_sp_surcharges_fixed_amount_required" in msg:
        raise HTTPException(status_code=422, detail="fixed_amount must be >= 0")

    raise HTTPException(status_code=409, detail="Conflict while saving surcharge")
