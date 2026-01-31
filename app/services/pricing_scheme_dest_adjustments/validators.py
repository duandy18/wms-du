# app/services/pricing_scheme_dest_adjustments/validators.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException

from app.geo.cn_registry import resolve_city, resolve_province


def norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def norm_required(s: Optional[str], field: str) -> str:
    s2 = norm(s)
    if not s2:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    return s2


def validate_scope(scope: Optional[str]) -> str:
    s = norm_required(scope, "scope").lower()
    if s not in ("province", "city"):
        raise HTTPException(status_code=422, detail="scope must be 'province' or 'city'")
    return s


def validate_amount(amount: object) -> Decimal:
    try:
        d = Decimal(str(amount))
    except Exception as e:
        raise HTTPException(status_code=422, detail="amount must be a number") from e
    if d.is_nan():
        raise HTTPException(status_code=422, detail="amount must be a number")
    if d < Decimal("0"):
        raise HTTPException(status_code=422, detail="amount must be >= 0")
    return d.quantize(Decimal("0.01"))


def resolve_province_code(province_code: Optional[str], province_name: Optional[str]) -> tuple[str, str]:
    """
    ✅ 强制标准：province_code 必须来自 geo 字典（或 name 可解析到字典项）。
    返回：(province_code, province_name)
    """
    item = resolve_province(code=province_code, name=province_name)
    if item is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "geo_invalid_province",
                "message": "invalid province (must match geo dictionary)",
                "province_code": norm(province_code),
                "province_name": norm(province_name),
            },
        )
    return item.code, item.name


def resolve_city_code(scope: str, province_code: str, city_code: Optional[str], city_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    ✅ 强制标准：
    - scope=province：city_code/city_name 必须为空
    - scope=city：city_code 必须来自该省的城市字典（或 name 可解析）
    返回：(city_code, city_name)
    """
    if scope == "province":
        return None, None

    item = resolve_city(province_code=province_code, code=city_code, name=city_name)
    if item is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "geo_invalid_city",
                "message": "invalid city (must match geo dictionary under province)",
                "province_code": province_code,
                "city_code": norm(city_code),
                "city_name": norm(city_name),
            },
        )
    return item.code, item.name
