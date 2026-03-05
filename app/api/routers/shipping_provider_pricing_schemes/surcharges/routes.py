# app/api/routers/shipping_provider_pricing_schemes/surcharges/routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_surcharge_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SurchargeCreateIn,
    SurchargeOut,
    SurchargeUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes.schemas.surcharge import SurchargeUpsertIn
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, norm_nonempty
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .helpers import (
    ensure_dest_mutual_exclusion,
    extract_dest_key_from_condition,
    reject_deprecated_amount_rounding,
)


def register_surcharges_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/surcharges",
        response_model=SurchargeOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_surcharge(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        # ✅ 拒绝废弃字段：amount_json.rounding
        reject_deprecated_amount_rounding(payload.amount_json)

        # ✅ 新合同护栏（若可解析出 dest key，则 enforce 互斥）
        k = extract_dest_key_from_condition(payload.condition_json or {})
        if k:
            scope2, prov2, _city2 = k
            ensure_dest_mutual_exclusion(
                db,
                scheme_id=scheme_id,
                target_scope=scope2,
                province=prov2,
                target_id=None,
                active=bool(payload.active),
            )

        s = ShippingProviderSurcharge(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
            condition_json=payload.condition_json,
            amount_json=payload.amount_json,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.post(
        "/pricing-schemes/{scheme_id}/surcharges:upsert",
        response_model=SurchargeOut,
        status_code=status.HTTP_200_OK,
    )
    def upsert_surcharge(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeUpsertIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        ✅ 新主入口（事实写入点）：
        - 输入：scope + province(+city) + amount
        - 行为：同 key 则更新，否则创建（幂等）
        - 护栏：同省 province vs city 互斥（active 时）
        """
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        scope2 = payload.scope
        prov2 = payload.province.strip()
        city2 = payload.city.strip() if payload.city else None

        condition_json = (
            {"dest": {"scope": "province", "province": prov2}}
            if scope2 == "province"
            else {"dest": {"scope": "city", "province": prov2, "city": city2}}
        )
        amount_json = {"kind": "flat", "amount": float(payload.amount)}
        reject_deprecated_amount_rounding(amount_json)

        # ✅ 互斥护栏：写前检查
        ensure_dest_mutual_exclusion(
            db,
            scheme_id=scheme_id,
            target_scope=scope2,
            province=prov2,
            target_id=None,
            active=bool(payload.active),
        )

        # ✅ 去重：同 key 查找（仅对可解析 key 的数据可靠）
        target: ShippingProviderSurcharge | None = None
        rows = (
            db.query(ShippingProviderSurcharge)
            .filter(ShippingProviderSurcharge.scheme_id == scheme_id)
            .order_by(ShippingProviderSurcharge.id.asc())
            .all()
        )
        for s in rows:
            k = extract_dest_key_from_condition(s.condition_json or {})
            if not k:
                continue
            sc, pv, ct = k
            if sc == scope2 and pv == prov2 and (ct or None) == (city2 or None):
                target = s
                break

        name = payload.name.strip() if isinstance(payload.name, str) and payload.name.strip() else None
        if not name:
            name = prov2 if scope2 == "province" else f"{prov2}-{city2}"

        if target is None:
            s = ShippingProviderSurcharge(
                scheme_id=scheme_id,
                name=norm_nonempty(name, "name"),
                active=bool(payload.active),
                condition_json=condition_json,
                amount_json=amount_json,
            )
            db.add(s)
            db.commit()
            db.refresh(s)
            return to_surcharge_out(s)

        # 更新（幂等）
        ensure_dest_mutual_exclusion(
            db,
            scheme_id=scheme_id,
            target_scope=scope2,
            province=prov2,
            target_id=int(target.id),
            active=bool(payload.active),
        )
        target.name = norm_nonempty(name, "name")
        target.active = bool(payload.active)
        target.condition_json = condition_json
        target.amount_json = amount_json
        db.commit()
        db.refresh(target)
        return to_surcharge_out(target)

    @router.patch(
        "/surcharges/{surcharge_id}",
        response_model=SurchargeOut,
    )
    def update_surcharge(
        surcharge_id: int = Path(..., ge=1),
        payload: SurchargeUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        data = payload.dict(exclude_unset=True)

        next_condition = (data.get("condition_json") if "condition_json" in data else s.condition_json) or {}
        next_active = bool(data["active"]) if "active" in data else bool(s.active)

        k = extract_dest_key_from_condition(next_condition)
        if k:
            scope2, prov2, _city2 = k
            ensure_dest_mutual_exclusion(
                db,
                scheme_id=int(s.scheme_id),
                target_scope=scope2,
                province=prov2,
                target_id=int(s.id),
                active=next_active,
            )

        if "name" in data:
            s.name = norm_nonempty(data.get("name"), "name")
        if "active" in data:
            s.active = bool(data["active"])
        if "condition_json" in data and data["condition_json"] is not None:
            s.condition_json = data["condition_json"]
        if "amount_json" in data and data["amount_json"] is not None:
            reject_deprecated_amount_rounding(data["amount_json"])
            s.amount_json = data["amount_json"]

        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.delete(
        "/surcharges/{surcharge_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_surcharge(
        surcharge_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        # ✅ 护栏：启用态不可删除，必须先停用（保持可解释/可审计）
        if bool(s.active):
            raise HTTPException(status_code=409, detail="must disable surcharge before delete")

        db.delete(s)
        db.commit()
        return {"ok": True}
