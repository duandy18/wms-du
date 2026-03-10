# app/api/routers/shipping_provider_pricing_schemes/surcharges/routes.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SurchargeCreateIn,
    SurchargeOut,
    SurchargeUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes.schemas.surcharge import SurchargeUpsertIn
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, norm_nonempty
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity


def _require_scheme(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return sch


def _norm(v: str | None) -> str:
    if v is None:
        return ""
    return v.strip()


def _province_identity_key(
    *,
    province_code: str | None,
    province_name: str | None,
) -> tuple[str, str]:
    return (_norm(province_code), _norm(province_name))


def _city_identity_key(
    *,
    city_code: str | None,
    city_name: str | None,
) -> tuple[str, str]:
    return (_norm(city_code), _norm(city_name))


def _require_province_payload(
    *,
    province_code: str | None,
) -> None:
    if not _norm(province_code):
        raise HTTPException(status_code=422, detail="province_code is required")


def _require_city_payload(
    *,
    city_code: str | None,
) -> None:
    if not _norm(city_code):
        raise HTTPException(status_code=422, detail="city_code is required")


def _find_config_for_province(
    db: Session,
    *,
    scheme_id: int,
    province_code: str | None,
    province_name: str | None,
) -> ShippingProviderSurchargeConfig | None:
    rows = (
        db.query(ShippingProviderSurchargeConfig)
        .options(selectinload(ShippingProviderSurchargeConfig.cities))
        .filter(ShippingProviderSurchargeConfig.scheme_id == int(scheme_id))
        .order_by(ShippingProviderSurchargeConfig.id.asc())
        .all()
    )

    target_key = _province_identity_key(
        province_code=province_code,
        province_name=province_name,
    )

    for row in rows:
        row_key = _province_identity_key(
            province_code=getattr(row, "province_code", None),
            province_name=getattr(row, "province_name", None),
        )
        if row_key[0] and target_key[0]:
            if row_key[0] == target_key[0]:
                return row
            continue
        if row_key[1] and target_key[1] and row_key[1] == target_key[1]:
            return row

    return None


def _find_city_row(
    cfg: ShippingProviderSurchargeConfig,
    *,
    city_code: str | None,
    city_name: str | None,
) -> ShippingProviderSurchargeConfigCity | None:
    target_key = _city_identity_key(city_code=city_code, city_name=city_name)

    for row in getattr(cfg, "cities", []) or []:
        row_key = _city_identity_key(
            city_code=getattr(row, "city_code", None),
            city_name=getattr(row, "city_name", None),
        )
        if row_key[0] and target_key[0]:
            if row_key[0] == target_key[0]:
                return row
            continue
        if row_key[1] and target_key[1] and row_key[1] == target_key[1]:
            return row

    return None


def _to_surcharge_out_from_config(
    cfg: ShippingProviderSurchargeConfig,
    city_row: ShippingProviderSurchargeConfigCity | None = None,
) -> SurchargeOut:
    if city_row is None:
        return SurchargeOut(
            id=int(cfg.id),
            scheme_id=int(cfg.scheme_id),
            name=str(getattr(cfg, "province_name", None) or getattr(cfg, "province_code", None) or f"cfg#{cfg.id}"),
            active=bool(cfg.active),
            scope="province",
            province_code=getattr(cfg, "province_code", None),
            city_code=None,
            province_name=getattr(cfg, "province_name", None),
            city_name=None,
            fixed_amount=getattr(cfg, "fixed_amount", Decimal("0")),
        )

    return SurchargeOut(
        id=int(city_row.id),
        scheme_id=int(cfg.scheme_id),
        name=str(
            f"{getattr(cfg, 'province_name', None) or getattr(cfg, 'province_code', None)}-"
            f"{getattr(city_row, 'city_name', None) or getattr(city_row, 'city_code', None)}"
        ),
        active=bool(city_row.active) and bool(cfg.active),
        scope="city",
        province_code=getattr(cfg, "province_code", None),
        city_code=getattr(city_row, "city_code", None),
        province_name=getattr(cfg, "province_name", None),
        city_name=getattr(city_row, "city_name", None),
        fixed_amount=getattr(city_row, "fixed_amount", Decimal("0")),
    )


def _upsert_province_mode_config(
    db: Session,
    *,
    scheme_id: int,
    province_code: str | None,
    province_name: str | None,
    amount: Decimal,
    active: bool,
) -> ShippingProviderSurchargeConfig:
    _require_province_payload(province_code=province_code)

    cfg = _find_config_for_province(
        db,
        scheme_id=scheme_id,
        province_code=province_code,
        province_name=province_name,
    )

    if cfg is None:
        cfg = ShippingProviderSurchargeConfig(
            scheme_id=int(scheme_id),
            province_code=norm_nonempty(province_code, "province_code"),
            province_name=_norm(province_name) or None,
            province_mode="province",
            fixed_amount=amount,
            active=bool(active),
        )
        db.add(cfg)
        db.flush()
        return cfg

    cfg.province_code = norm_nonempty(province_code, "province_code")
    cfg.province_name = _norm(province_name) or getattr(cfg, "province_name", None)
    cfg.province_mode = "province"
    cfg.fixed_amount = amount
    cfg.active = bool(active)

    # 切回全省模式时，删掉子城市规则，避免脏数据继续躺尸
    for row in list(getattr(cfg, "cities", []) or []):
        db.delete(row)

    db.flush()
    return cfg


def _upsert_city_mode_config(
    db: Session,
    *,
    scheme_id: int,
    province_code: str | None,
    province_name: str | None,
    city_code: str | None,
    city_name: str | None,
    amount: Decimal,
    active: bool,
) -> tuple[ShippingProviderSurchargeConfig, ShippingProviderSurchargeConfigCity]:
    _require_province_payload(province_code=province_code)
    _require_city_payload(city_code=city_code)

    cfg = _find_config_for_province(
        db,
        scheme_id=scheme_id,
        province_code=province_code,
        province_name=province_name,
    )

    if cfg is None:
        cfg = ShippingProviderSurchargeConfig(
            scheme_id=int(scheme_id),
            province_code=norm_nonempty(province_code, "province_code"),
            province_name=_norm(province_name) or None,
            province_mode="cities",
            fixed_amount=Decimal("0"),
            active=bool(active),
        )
        db.add(cfg)
        db.flush()
    else:
        cfg.province_code = norm_nonempty(province_code, "province_code")
        cfg.province_name = _norm(province_name) or getattr(cfg, "province_name", None)
        cfg.province_mode = "cities"
        cfg.fixed_amount = Decimal("0")
        cfg.active = bool(active)
        db.flush()

    city_row = _find_city_row(
        cfg,
        city_code=city_code,
        city_name=city_name,
    )

    if city_row is None:
        city_row = ShippingProviderSurchargeConfigCity(
            config_id=int(cfg.id),
            city_code=norm_nonempty(city_code, "city_code"),
            city_name=_norm(city_name) or None,
            fixed_amount=amount,
            active=bool(active),
        )
        db.add(city_row)
        db.flush()
        return cfg, city_row

    city_row.city_code = norm_nonempty(city_code, "city_code")
    city_row.city_name = _norm(city_name) or getattr(city_row, "city_name", None)
    city_row.fixed_amount = amount
    city_row.active = bool(active)
    db.flush()
    return cfg, city_row


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
        _require_scheme(db, scheme_id)

        scope = (payload.scope or "").strip().lower()
        amount = Decimal(payload.fixed_amount)

        if scope == "province":
            cfg = _upsert_province_mode_config(
                db,
                scheme_id=scheme_id,
                province_code=payload.province_code,
                province_name=payload.province_name,
                amount=amount,
                active=bool(payload.active),
            )
            db.commit()
            db.refresh(cfg)
            return _to_surcharge_out_from_config(cfg)

        if scope == "city":
            cfg, city_row = _upsert_city_mode_config(
                db,
                scheme_id=scheme_id,
                province_code=payload.province_code,
                province_name=payload.province_name,
                city_code=payload.city_code,
                city_name=payload.city_name,
                amount=amount,
                active=bool(payload.active),
            )
            db.commit()
            db.refresh(cfg)
            db.refresh(city_row)
            return _to_surcharge_out_from_config(cfg, city_row)

        raise HTTPException(status_code=422, detail="scope must be one of: province / city")

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
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        amount = Decimal(payload.amount)

        if payload.scope == "province":
            cfg = _upsert_province_mode_config(
                db,
                scheme_id=scheme_id,
                province_code=payload.province_code,
                province_name=payload.province_name,
                amount=amount,
                active=bool(payload.active),
            )
            db.commit()
            db.refresh(cfg)
            return _to_surcharge_out_from_config(cfg)

        cfg, city_row = _upsert_city_mode_config(
            db,
            scheme_id=scheme_id,
            province_code=payload.province_code,
            province_name=payload.province_name,
            city_code=payload.city_code,
            city_name=payload.city_name,
            amount=amount,
            active=bool(payload.active),
        )
        db.commit()
        db.refresh(cfg)
        db.refresh(city_row)
        return _to_surcharge_out_from_config(cfg, city_row)

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

        city_row = db.get(ShippingProviderSurchargeConfigCity, surcharge_id)
        if city_row is not None:
            cfg = (
                db.query(ShippingProviderSurchargeConfig)
                .options(selectinload(ShippingProviderSurchargeConfig.cities))
                .filter(ShippingProviderSurchargeConfig.id == int(city_row.config_id))
                .one()
            )

            data = payload.model_dump(exclude_unset=True)

            if "active" in data and data["active"] is not None:
                city_row.active = bool(data["active"])
            if "city_code" in data and data["city_code"] is not None:
                city_row.city_code = norm_nonempty(data["city_code"], "city_code")
            if "city_name" in data:
                city_row.city_name = _norm(data["city_name"]) or None
            if "fixed_amount" in data and data["fixed_amount"] is not None:
                city_row.fixed_amount = Decimal(data["fixed_amount"])

            if "province_code" in data and data["province_code"] is not None:
                cfg.province_code = norm_nonempty(data["province_code"], "province_code")
            if "province_name" in data:
                cfg.province_name = _norm(data["province_name"]) or None

            db.commit()
            db.refresh(cfg)
            db.refresh(city_row)
            return _to_surcharge_out_from_config(cfg, city_row)

        cfg = (
            db.query(ShippingProviderSurchargeConfig)
            .options(selectinload(ShippingProviderSurchargeConfig.cities))
            .filter(ShippingProviderSurchargeConfig.id == surcharge_id)
            .one_or_none()
        )
        if cfg is None:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        data = payload.model_dump(exclude_unset=True)

        if "active" in data and data["active"] is not None:
            cfg.active = bool(data["active"])
        if "province_code" in data and data["province_code"] is not None:
            cfg.province_code = norm_nonempty(data["province_code"], "province_code")
        if "province_name" in data:
            cfg.province_name = _norm(data["province_name"]) or None
        if "fixed_amount" in data and data["fixed_amount"] is not None:
            cfg.fixed_amount = Decimal(data["fixed_amount"])

        # config 本身只允许表示省模式
        if "scope" in data and data["scope"] is not None:
            next_scope = str(data["scope"]).strip().lower()
            if next_scope != "province":
                raise HTTPException(status_code=409, detail="config row can only be updated as province scope")

        cfg.province_mode = "province"

        for row in list(getattr(cfg, "cities", []) or []):
            db.delete(row)

        db.commit()
        db.refresh(cfg)
        return _to_surcharge_out_from_config(cfg)

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

        city_row = db.get(ShippingProviderSurchargeConfigCity, surcharge_id)
        if city_row is not None:
            if bool(city_row.active):
                raise HTTPException(status_code=409, detail="must disable surcharge before delete")
            db.delete(city_row)
            db.commit()
            return {"ok": True}

        cfg = db.get(ShippingProviderSurchargeConfig, surcharge_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        if bool(cfg.active):
            raise HTTPException(status_code=409, detail="must disable surcharge before delete")

        db.delete(cfg)
        db.commit()
        return {"ok": True}
