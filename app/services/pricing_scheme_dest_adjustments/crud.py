# app/services/pricing_scheme_dest_adjustments/crud.py
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from .conflicts import ensure_dest_adjustment_mutual_exclusion
from .validators import (
    norm,
    resolve_city_code,
    resolve_province_code,
    validate_amount,
    validate_scope,
)


def _require_code(v: Optional[str], field: str) -> str:
    t = norm(v)
    if not t:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "geo_missing_code",
                "message": f"{field} is required (must be geo code)",
                "field": field,
            },
        )
    return t


def upsert_dest_adjustment(
    db: Session,
    *,
    scheme_id: int,
    scope: str,
    province_code: Optional[str] = None,
    city_code: Optional[str] = None,
    # ✅ 展示字段：允许不传（后端会按字典填充标准 name）
    province_name: Optional[str] = None,
    city_name: Optional[str] = None,
    # ❌ legacy 输入：一律不接受（保留签名只是为了不让旧调用点直接炸 import）
    province: Optional[str] = None,
    city: Optional[str] = None,
    amount: object,
    active: bool,
    priority: Optional[int] = None,
) -> PricingSchemeDestAdjustment:
    """
    ✅ 事实写入点（幂等，严格 code 世界）：
      - key: (scheme_id, scope, province_code, city_code)
      - 仅接受标准 GB2260 code；不再接受 legacy province/city 字符串输入
    """
    sch = db.get(ShippingProviderPricingScheme, int(scheme_id))
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    scope2 = validate_scope(scope)

    # ✅ 禁止 legacy 写入（避免旧路径复活）
    if norm(province) or norm(city):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "geo_legacy_input_forbidden",
                "message": "legacy province/city input is forbidden; use province_code/city_code",
            },
        )

    prov_code_raw = _require_code(province_code, "province_code")
    # 使用字典校验并补全标准 name（允许 province_name 为空）
    prov_code2, prov_name2 = resolve_province_code(prov_code_raw, province_name)

    city_code2: Optional[str] = None
    city_name2: Optional[str] = None
    if scope2 == "city":
        city_code_raw = _require_code(city_code, "city_code")
        city_code2, city_name2 = resolve_city_code(scope2, prov_code2, city_code_raw, city_name)

    amt = validate_amount(amount)
    pri = int(priority) if priority is not None else 100

    target: PricingSchemeDestAdjustment | None = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(scheme_id))
        .filter(PricingSchemeDestAdjustment.scope == scope2)
        .filter(PricingSchemeDestAdjustment.province_code == prov_code2)
        .filter(
            PricingSchemeDestAdjustment.city_code.is_(city_code2)
            if city_code2 is None
            else PricingSchemeDestAdjustment.city_code == city_code2
        )
        .one_or_none()
    )

    if target is None:
        ensure_dest_adjustment_mutual_exclusion(
            db,
            scheme_id=int(scheme_id),
            target_scope=scope2,
            province_code=prov_code2,
            target_id=None,
            active=bool(active),
        )
        target = PricingSchemeDestAdjustment(
            scheme_id=int(scheme_id),
            scope=scope2,
            province_code=prov_code2,
            city_code=city_code2,
            province_name=prov_name2,
            city_name=city_name2,
            # ✅ 输出兼容字段：由标准 name 回填（但不再接受输入）
            province=prov_name2,
            city=city_name2,
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
        province_code=prov_code2,
        target_id=int(target.id),
        active=bool(active),
    )

    target.scope = scope2
    target.province_code = prov_code2
    target.city_code = city_code2
    target.province_name = prov_name2
    target.city_name = city_name2

    # ✅ 输出兼容字段：同步为标准 name
    target.province = prov_name2
    target.city = city_name2

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
    province_code: Optional[str] = None,
    city_code: Optional[str] = None,
    province_name: Optional[str] = None,
    city_name: Optional[str] = None,
    # ❌ legacy 输入：一律不接受
    province: Optional[str] = None,
    city: Optional[str] = None,
    amount: Optional[object] = None,
    active: Optional[bool] = None,
    priority: Optional[int] = None,
) -> PricingSchemeDestAdjustment:
    """
    ✅ patch 入口（严格 code 世界）：
      - 常用：改 amount/active/priority
      - 允许改 scope/province_code/city_code，但必须是字典内合法 code
      - 不再接受 legacy province/city 输入
    """
    row = db.get(PricingSchemeDestAdjustment, int(dest_adjustment_id))
    if not row:
        raise HTTPException(status_code=404, detail="Dest adjustment not found")

    if norm(province) or norm(city):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "geo_legacy_input_forbidden",
                "message": "legacy province/city input is forbidden; use province_code/city_code",
            },
        )

    next_scope = validate_scope(scope) if scope is not None else str(row.scope)

    # 如果用户要改 province_code：必须提供 code（并通过字典校验）
    if province_code is not None:
        prov_code_raw = _require_code(province_code, "province_code")
        next_prov_code, next_prov_name = resolve_province_code(prov_code_raw, province_name)
    else:
        # 不改 code：仍可用字典补齐 name（若 name 为空）
        next_prov_code, next_prov_name = resolve_province_code(str(row.province_code), province_name or row.province_name)

    next_city_code: Optional[str] = None
    next_city_name: Optional[str] = None

    if next_scope == "city":
        # city scope 下：若用户提供 city_code，则用之；否则沿用 row.city_code
        raw_city = city_code if city_code is not None else row.city_code
        raw_city = _require_code(raw_city, "city_code")
        next_city_code, next_city_name = resolve_city_code(next_scope, next_prov_code, raw_city, city_name or row.city_name)
    else:
        next_city_code, next_city_name = None, None

    next_amt = validate_amount(amount) if amount is not None else validate_amount(row.amount)
    next_active = bool(active) if active is not None else bool(row.active)
    next_pri = int(priority) if priority is not None else int(row.priority or 100)

    dup = (
        db.query(PricingSchemeDestAdjustment)
        .filter(PricingSchemeDestAdjustment.scheme_id == int(row.scheme_id))
        .filter(PricingSchemeDestAdjustment.scope == next_scope)
        .filter(PricingSchemeDestAdjustment.province_code == next_prov_code)
        .filter(
            PricingSchemeDestAdjustment.city_code.is_(next_city_code)
            if next_city_code is None
            else PricingSchemeDestAdjustment.city_code == next_city_code
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
        province_code=next_prov_code,
        target_id=int(row.id),
        active=next_active,
    )

    row.scope = next_scope
    row.province_code = next_prov_code
    row.city_code = next_city_code
    row.province_name = next_prov_name
    row.city_name = next_city_name

    # ✅ 输出兼容字段同步
    row.province = next_prov_name
    row.city = next_city_name

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
