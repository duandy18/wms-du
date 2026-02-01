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


def _is_municipality_province_code(province_code: str) -> bool:
    pc = norm(province_code) or ""
    return pc in {"110000", "120000", "310000", "500000"}


def _municipality_city_code_from_prov_code(province_code: str) -> str:
    pc = norm(province_code) or ""
    try:
        n = int(pc)
    except Exception:
        return ""
    return str(n + 100).zfill(6)


def resolve_city_code(scope: str, province_code: str, city_code: Optional[str], city_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    ✅ 强制标准：
    - scope=province：city_code/city_name 必须为空（由调用方护栏确保）
    - scope=city：
        - 普通省份：city_code 必须来自该省的城市字典（或 name 可解析）
        - 直辖市：city_code 只允许唯一市码（xx0100），且不依赖 city 字典（避免字典为空导致无法配置）
    返回：(city_code, city_name)
    """
    if scope == "province":
        return None, None

    prov_code = norm(province_code) or ""
    if _is_municipality_province_code(prov_code):
        expected = _municipality_city_code_from_prov_code(prov_code)
        cc = norm(city_code)
        if not cc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "geo_missing_code",
                    "message": "city_code is required (must be geo code)",
                    "field": "city_code",
                },
            )
        if expected and cc != expected:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "geo_invalid_municipality_city",
                    "message": "invalid city for municipality (must be the unique municipality city code)",
                    "province_code": prov_code,
                    "city_code": cc,
                    "expected_city_code": expected,
                },
            )

        # ✅ 直辖市 city_name 规范化：优先用省字典名（例如 北京市）
        prov_item = resolve_province(code=prov_code, name=None)
        std_name = prov_item.name if prov_item is not None else (norm(city_name) or "")
        return cc, (std_name or None)

    # 普通省份：走城市字典校验
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
