# app/api/routers/shipping_provider_pricing_schemes/surcharges/helpers.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def reject_deprecated_amount_rounding(amount_json: object) -> None:
    """
    ✅ 护栏：amount_json.rounding 已废弃且不再生效。

    取整唯一来源：
      scheme.billable_weight_rule.rounding
    且只在 _compute_billable_weight_kg 中执行一次（避免 double-rounding）。

    为避免继续产生“新债”，写入口一律拒绝 amount_json.rounding。
    """
    if not isinstance(amount_json, dict):
        return
    if "rounding" in amount_json and amount_json.get("rounding") is not None:
        raise HTTPException(
            status_code=422,
            detail="amount_json.rounding is deprecated and ignored; use scheme.billable_weight_rule.rounding",
        )


def extract_dest_key_from_condition(condition_json: dict) -> tuple[str, str, str | None] | None:
    """
    解析我们约定的新结构（优先）：

      {"dest":{"scope":"province","province":"广东省"}}
      {"dest":{"scope":"city","province":"广东省","city":"深圳市"}}

    同时兼容旧结构（仅当数组长度=1）：
      {"dest":{"province":["广东省"]}}
      {"dest":{"province":["广东省"],"city":["深圳市"]}}

    返回：(scope, province, city?)
    """
    if not isinstance(condition_json, dict):
        return None
    dest = condition_json.get("dest")
    if not isinstance(dest, dict):
        return None

    scope = dest.get("scope")
    prov = dest.get("province")
    city = dest.get("city")

    # 新结构（scope + 单值）
    if isinstance(scope, str) and scope.strip().lower() in ("province", "city"):
        scope2 = scope.strip().lower()
        if isinstance(prov, str) and prov.strip():
            prov2 = prov.strip()
        else:
            return None
        if scope2 == "province":
            return ("province", prov2, None)
        # city
        if isinstance(city, str) and city.strip():
            return ("city", prov2, city.strip())
        return None

    # 旧结构（列表）
    provs = dest.get("province")
    cities = dest.get("city")
    if isinstance(provs, list) and len(provs) == 1 and isinstance(provs[0], str) and provs[0].strip():
        prov2 = provs[0].strip()
        if isinstance(cities, list) and len(cities) == 1 and isinstance(cities[0], str) and cities[0].strip():
            return ("city", prov2, cities[0].strip())
        if cities is None or (isinstance(cities, list) and len(cities) == 0):
            return ("province", prov2, None)

    return None


def ensure_dest_mutual_exclusion(
    db: Session,
    *,
    scheme_id: int,
    target_scope: str,
    province: str,
    target_id: int | None,
    active: bool,
) -> None:
    """
    ✅ 护栏：同一省份：
      - province 规则 与 任意 city 规则 不允许同时 active
    仅对“我们能解析出 dest key 的规则”强制执行。
    """
    if not active:
        return

    province = (province or "").strip()
    if not province:
        return

    q = (
        db.query(ShippingProviderSurcharge)
        .filter(
            ShippingProviderSurcharge.scheme_id == int(scheme_id),
            ShippingProviderSurcharge.active.is_(True),
        )
        .order_by(ShippingProviderSurcharge.id.asc())
    )
    if target_id is not None:
        q = q.filter(ShippingProviderSurcharge.id != int(target_id))

    rows = q.all()
    for s in rows:
        k = extract_dest_key_from_condition(s.condition_json or {})
        if not k:
            continue
        scope2, prov2, _city2 = k
        if prov2 != province:
            continue

        # 同省冲突：province vs city
        if target_scope == "province" and scope2 == "city":
            raise HTTPException(
                status_code=409,
                detail=f"conflict: province surcharge cannot be active when city surcharges exist for province={province}",
            )
        if target_scope == "city" and scope2 == "province":
            raise HTTPException(
                status_code=409,
                detail=f"conflict: city surcharge cannot be active when province surcharge exists for province={province}",
            )
