# app/api/routers/shipping_provider_pricing_schemes/surcharge_configs/routes.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.surcharge import (
    SurchargeConfigBatchProvinceCreateIn,
    SurchargeConfigBatchProvinceCreateOut,
    SurchargeConfigCreateIn,
    SurchargeConfigOut,
    SurchargeConfigUpdateIn,
    SurchargeCityContainerCreateIn,
)
from app.api.routers.shipping_provider_pricing_schemes_mappers import (
    to_surcharge_config_out,
)
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


def _find_config_for_province(
    db: Session,
    *,
    scheme_id: int,
    province_code: str,
) -> ShippingProviderSurchargeConfig | None:
    return (
        db.query(ShippingProviderSurchargeConfig)
        .options(selectinload(ShippingProviderSurchargeConfig.cities))
        .filter(
            ShippingProviderSurchargeConfig.scheme_id == int(scheme_id),
            ShippingProviderSurchargeConfig.province_code == str(province_code),
        )
        .one_or_none()
    )


def _load_config_or_404(
    db: Session,
    *,
    config_id: int,
) -> ShippingProviderSurchargeConfig:
    cfg = (
        db.query(ShippingProviderSurchargeConfig)
        .options(selectinload(ShippingProviderSurchargeConfig.cities))
        .filter(ShippingProviderSurchargeConfig.id == int(config_id))
        .one_or_none()
    )
    if cfg is None:
        raise HTTPException(status_code=404, detail="Surcharge config not found")
    return cfg


def _validate_config_payload_for_write(
    *,
    province_mode: str,
    fixed_amount: Decimal | None,
    cities_count: int,
) -> None:
    mode = str(province_mode).strip().lower()

    if mode == "province":
        if fixed_amount is None:
            raise HTTPException(status_code=422, detail="fixed_amount is required when province_mode=province")
        if cities_count != 0:
            raise HTTPException(status_code=422, detail="cities must be empty when province_mode=province")
        return

    if mode == "cities":
        if fixed_amount is not None and Decimal(fixed_amount) != Decimal("0"):
            raise HTTPException(status_code=422, detail="fixed_amount must be 0 when province_mode=cities")
        return

    raise HTTPException(status_code=422, detail="province_mode must be one of: province / cities")


def _sync_config_cities(
    db: Session,
    *,
    cfg: ShippingProviderSurchargeConfig,
    cities_payload,
) -> None:
    existing_by_code = {
        str(row.city_code): row
        for row in (getattr(cfg, "cities", []) or [])
    }

    next_codes: set[str] = set()

    for item in cities_payload:
        city_code = norm_nonempty(item.city_code, "city_code")
        city_name = _norm(item.city_name) or None
        fixed_amount = Decimal(item.fixed_amount)
        active = bool(item.active)

        next_codes.add(city_code)

        row = existing_by_code.get(city_code)
        if row is None:
            db.add(
                ShippingProviderSurchargeConfigCity(
                    config_id=int(cfg.id),
                    city_code=city_code,
                    city_name=city_name,
                    fixed_amount=fixed_amount,
                    active=active,
                )
            )
            continue

        row.city_code = city_code
        row.city_name = city_name
        row.fixed_amount = fixed_amount
        row.active = active

    for row in list(getattr(cfg, "cities", []) or []):
        if str(row.city_code) not in next_codes:
            db.delete(row)


def _delete_all_config_cities(db: Session, *, cfg: ShippingProviderSurchargeConfig) -> None:
    for row in list(getattr(cfg, "cities", []) or []):
        db.delete(row)
    db.flush()


def _create_config_row(
    db: Session,
    *,
    scheme_id: int,
    province_code: str,
    province_name: str | None,
    province_mode: str,
    fixed_amount: Decimal,
    active: bool,
) -> ShippingProviderSurchargeConfig:
    cfg = ShippingProviderSurchargeConfig(
        scheme_id=int(scheme_id),
        province_code=province_code,
        province_name=province_name,
        province_mode=province_mode,
        fixed_amount=fixed_amount,
        active=active,
    )
    db.add(cfg)
    db.flush()
    return cfg


def register_surcharge_config_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/surcharge-configs/batch-province",
        response_model=SurchargeConfigBatchProvinceCreateOut,
        status_code=status.HTTP_201_CREATED,
    )
    def batch_create_province_surcharge_configs(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeConfigBatchProvinceCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        created_ids: list[int] = []
        skipped: list[dict[str, str | None]] = []
        seen_codes: set[str] = set()

        for item in payload.items:
            province_code = norm_nonempty(item.province_code, "province_code")
            province_name = _norm(item.province_name) or None
            fixed_amount = Decimal(item.fixed_amount)
            active = bool(item.active)

            if province_code in seen_codes:
                skipped.append(
                    {
                        "province_code": province_code,
                        "province_name": province_name,
                        "reason": "duplicate_in_payload",
                    }
                )
                continue
            seen_codes.add(province_code)

            exists = _find_config_for_province(
                db,
                scheme_id=scheme_id,
                province_code=province_code,
            )
            if exists is not None:
                skipped.append(
                    {
                        "province_code": province_code,
                        "province_name": province_name,
                        "reason": "already_exists",
                    }
                )
                continue

            cfg = _create_config_row(
                db,
                scheme_id=scheme_id,
                province_code=province_code,
                province_name=province_name,
                province_mode="province",
                fixed_amount=fixed_amount,
                active=active,
            )
            created_ids.append(int(cfg.id))

        db.commit()

        created = [
            to_surcharge_config_out(_load_config_or_404(db, config_id=config_id))
            for config_id in created_ids
        ]
        return {
            "created": created,
            "skipped": skipped,
        }

    @router.post(
        "/pricing-schemes/{scheme_id}/surcharge-configs/city-container",
        response_model=SurchargeConfigOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_surcharge_city_container(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeCityContainerCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        province_code = norm_nonempty(payload.province_code, "province_code")
        province_name = _norm(payload.province_name) or None
        active = bool(payload.active)

        exists = _find_config_for_province(
            db,
            scheme_id=scheme_id,
            province_code=province_code,
        )
        if exists is not None:
            raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

        cfg = _create_config_row(
            db,
            scheme_id=scheme_id,
            province_code=province_code,
            province_name=province_name,
            province_mode="cities",
            fixed_amount=Decimal("0"),
            active=active,
        )

        db.commit()
        cfg = _load_config_or_404(db, config_id=int(cfg.id))
        return to_surcharge_config_out(cfg)

    @router.post(
        "/pricing-schemes/{scheme_id}/surcharge-configs",
        response_model=SurchargeConfigOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_surcharge_config(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeConfigCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        _require_scheme(db, scheme_id)

        province_code = norm_nonempty(payload.province_code, "province_code")
        province_name = _norm(payload.province_name) or None
        province_mode = str(payload.province_mode).strip().lower()
        fixed_amount = Decimal(payload.fixed_amount)
        active = bool(payload.active)

        _validate_config_payload_for_write(
            province_mode=province_mode,
            fixed_amount=fixed_amount,
            cities_count=len(payload.cities),
        )

        exists = _find_config_for_province(
            db,
            scheme_id=scheme_id,
            province_code=province_code,
        )
        if exists is not None:
            raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

        cfg = _create_config_row(
            db,
            scheme_id=scheme_id,
            province_code=province_code,
            province_name=province_name,
            province_mode=province_mode,
            fixed_amount=fixed_amount if province_mode == "province" else Decimal("0"),
            active=active,
        )

        if province_mode == "cities":
            _sync_config_cities(
                db,
                cfg=cfg,
                cities_payload=payload.cities,
            )

        db.commit()
        cfg = _load_config_or_404(db, config_id=int(cfg.id))
        return to_surcharge_config_out(cfg)

    @router.patch(
        "/surcharge-configs/{config_id}",
        response_model=SurchargeConfigOut,
    )
    def update_surcharge_config(
        config_id: int = Path(..., ge=1),
        payload: SurchargeConfigUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        cfg = _load_config_or_404(db, config_id=config_id)
        data = payload.model_dump(exclude_unset=True)

        next_province_code = (
            norm_nonempty(data["province_code"], "province_code")
            if "province_code" in data and data["province_code"] is not None
            else str(cfg.province_code)
        )
        next_province_name = (
            _norm(data["province_name"]) or None
            if "province_name" in data
            else cfg.province_name
        )
        next_province_mode = (
            str(data["province_mode"]).strip().lower()
            if "province_mode" in data and data["province_mode"] is not None
            else str(cfg.province_mode)
        )
        next_fixed_amount = (
            Decimal(data["fixed_amount"])
            if "fixed_amount" in data and data["fixed_amount"] is not None
            else Decimal(cfg.fixed_amount)
        )
        next_active = (
            bool(data["active"])
            if "active" in data and data["active"] is not None
            else bool(cfg.active)
        )
        next_cities_payload = (
            list(payload.cities or [])
            if "cities" in data
            else list(getattr(cfg, "cities", []) or [])
        )

        if next_province_code != str(cfg.province_code):
            exists = _find_config_for_province(
                db,
                scheme_id=int(cfg.scheme_id),
                province_code=next_province_code,
            )
            if exists is not None and int(exists.id) != int(cfg.id):
                raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

        _validate_config_payload_for_write(
            province_mode=next_province_mode,
            fixed_amount=next_fixed_amount,
            cities_count=len(next_cities_payload),
        )

        # 关键顺序：
        # cities -> province 切换时，必须先删光 city rows，再把 config 改成 province。
        # 否则 DB trigger 会在 config UPDATE 时看到“province 模式仍挂 city rows”而拒绝提交。
        if next_province_mode == "province":
            _delete_all_config_cities(db, cfg=cfg)

            cfg.province_code = next_province_code
            cfg.province_name = next_province_name
            cfg.province_mode = next_province_mode
            cfg.active = next_active
            cfg.fixed_amount = next_fixed_amount
        else:
            cfg.province_code = next_province_code
            cfg.province_name = next_province_name
            cfg.province_mode = next_province_mode
            cfg.active = next_active
            cfg.fixed_amount = Decimal("0")
            _sync_config_cities(
                db,
                cfg=cfg,
                cities_payload=next_cities_payload,
            )

        db.commit()
        cfg = _load_config_or_404(db, config_id=int(cfg.id))
        return to_surcharge_config_out(cfg)

    @router.delete(
        "/surcharge-configs/{config_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_surcharge_config(
        config_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        cfg = db.get(ShippingProviderSurchargeConfig, config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Surcharge config not found")

        db.delete(cfg)
        db.commit()
        return {"ok": True}
