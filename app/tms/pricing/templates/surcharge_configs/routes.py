from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session, selectinload

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.pricing.templates.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.pricing.templates.models.shipping_provider_pricing_template_surcharge_config import (
    ShippingProviderPricingTemplateSurchargeConfig,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_surcharge_config_city import (
    ShippingProviderPricingTemplateSurchargeConfigCity,
)
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.module_resources_shared import (
    ensure_template_draft,
    load_template_or_404,
)
from app.tms.pricing.templates.contracts.surcharge import (
    SurchargeConfigBatchProvinceCreateIn,
    SurchargeConfigBatchProvinceCreateOut,
    SurchargeConfigCreateIn,
    SurchargeConfigOut,
    SurchargeConfigUpdateIn,
    SurchargeCityContainerCreateIn,
)


router = APIRouter()


def _require_template_draft(db: Session, template_id: int) -> ShippingProviderPricingTemplate:
    row = load_template_or_404(db, template_id)
    ensure_template_draft(row)
    return row


def _norm(v: str | None) -> str:
    if v is None:
        return ""
    return v.strip()


def _norm_nonempty(v: str | None, field_name: str) -> str:
    s = _norm(v)
    if not s:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return s


def _find_config_for_province(
    db: Session,
    *,
    template_id: int,
    province_code: str,
) -> ShippingProviderPricingTemplateSurchargeConfig | None:
    return (
        db.query(ShippingProviderPricingTemplateSurchargeConfig)
        .options(selectinload(ShippingProviderPricingTemplateSurchargeConfig.cities))
        .filter(
            ShippingProviderPricingTemplateSurchargeConfig.template_id == int(template_id),
            ShippingProviderPricingTemplateSurchargeConfig.province_code == str(province_code),
        )
        .one_or_none()
    )


def _load_config_or_404(
    db: Session,
    *,
    config_id: int,
) -> ShippingProviderPricingTemplateSurchargeConfig:
    cfg = (
        db.query(ShippingProviderPricingTemplateSurchargeConfig)
        .options(selectinload(ShippingProviderPricingTemplateSurchargeConfig.cities))
        .filter(ShippingProviderPricingTemplateSurchargeConfig.id == int(config_id))
        .one_or_none()
    )
    if cfg is None:
        raise HTTPException(status_code=404, detail="Surcharge config not found")
    return cfg


def _to_surcharge_config_out(
    cfg: ShippingProviderPricingTemplateSurchargeConfig,
) -> SurchargeConfigOut:
    cities = sorted(
        list(getattr(cfg, "cities", []) or []),
        key=lambda x: (str(x.city_code), int(x.id)),
    )

    return SurchargeConfigOut(
        id=int(cfg.id),
        template_id=int(cfg.template_id),
        province_code=str(cfg.province_code),
        province_name=cfg.province_name,
        province_mode=str(cfg.province_mode),
        fixed_amount=cfg.fixed_amount,
        active=bool(cfg.active),
        cities=[
            {
                "id": int(city.id),
                "config_id": int(city.config_id),
                "city_code": str(city.city_code),
                "city_name": city.city_name,
                "fixed_amount": city.fixed_amount,
                "active": bool(city.active),
            }
            for city in cities
        ],
    )


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
    cfg: ShippingProviderPricingTemplateSurchargeConfig,
    cities_payload,
) -> None:
    existing_by_code = {
        str(row.city_code): row
        for row in (getattr(cfg, "cities", []) or [])
    }

    next_codes: set[str] = set()

    for item in cities_payload:
        city_code = _norm_nonempty(item.city_code, "city_code")
        city_name = _norm(item.city_name) or None
        fixed_amount = Decimal(item.fixed_amount)
        active = bool(item.active)

        next_codes.add(city_code)

        row = existing_by_code.get(city_code)
        if row is None:
            db.add(
                ShippingProviderPricingTemplateSurchargeConfigCity(
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


def _delete_all_config_cities(
    db: Session,
    *,
    cfg: ShippingProviderPricingTemplateSurchargeConfig,
) -> None:
    for row in list(getattr(cfg, "cities", []) or []):
        db.delete(row)
    db.flush()


def _create_config_row(
    db: Session,
    *,
    template_id: int,
    province_code: str,
    province_name: str | None,
    province_mode: str,
    fixed_amount: Decimal,
    active: bool,
) -> ShippingProviderPricingTemplateSurchargeConfig:
    cfg = ShippingProviderPricingTemplateSurchargeConfig(
        template_id=int(template_id),
        province_code=province_code,
        province_name=province_name,
        province_mode=province_mode,
        fixed_amount=fixed_amount,
        active=active,
    )
    db.add(cfg)
    db.flush()
    return cfg


@router.post(
    "/templates/{template_id}/surcharge-configs/batch-province",
    response_model=SurchargeConfigBatchProvinceCreateOut,
    status_code=status.HTTP_201_CREATED,
    name="pricing_template_surcharge_batch_province",
)
def batch_create_province_surcharge_configs(
    template_id: int = Path(..., ge=1),
    payload: SurchargeConfigBatchProvinceCreateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])
    _require_template_draft(db, template_id)

    created_ids: list[int] = []
    skipped: list[dict[str, str | None]] = []
    seen_codes: set[str] = set()

    for item in payload.items:
        province_code = _norm_nonempty(item.province_code, "province_code")
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
            template_id=template_id,
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
            template_id=template_id,
            province_code=province_code,
            province_name=province_name,
            province_mode="province",
            fixed_amount=fixed_amount,
            active=active,
        )
        created_ids.append(int(cfg.id))

    db.commit()

    created = [
        _to_surcharge_config_out(_load_config_or_404(db, config_id=config_id))
        for config_id in created_ids
    ]
    return {
        "created": created,
        "skipped": skipped,
    }


@router.post(
    "/templates/{template_id}/surcharge-configs/city-container",
    response_model=SurchargeConfigOut,
    status_code=status.HTTP_201_CREATED,
    name="pricing_template_surcharge_city_container_create",
)
def create_surcharge_city_container(
    template_id: int = Path(..., ge=1),
    payload: SurchargeCityContainerCreateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])
    _require_template_draft(db, template_id)

    province_code = _norm_nonempty(payload.province_code, "province_code")
    province_name = _norm(payload.province_name) or None
    active = bool(payload.active)

    exists = _find_config_for_province(
        db,
        template_id=template_id,
        province_code=province_code,
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

    cfg = _create_config_row(
        db,
        template_id=template_id,
        province_code=province_code,
        province_name=province_name,
        province_mode="cities",
        fixed_amount=Decimal("0"),
        active=active,
    )

    db.commit()
    cfg = _load_config_or_404(db, config_id=int(cfg.id))
    return _to_surcharge_config_out(cfg)


@router.post(
    "/templates/{template_id}/surcharge-configs",
    response_model=SurchargeConfigOut,
    status_code=status.HTTP_201_CREATED,
    name="pricing_template_surcharge_create",
)
def create_surcharge_config(
    template_id: int = Path(..., ge=1),
    payload: SurchargeConfigCreateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])
    _require_template_draft(db, template_id)

    province_code = _norm_nonempty(payload.province_code, "province_code")
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
        template_id=template_id,
        province_code=province_code,
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

    cfg = _create_config_row(
        db,
        template_id=template_id,
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
    return _to_surcharge_config_out(cfg)


@router.patch(
    "/surcharge-configs/{config_id}",
    response_model=SurchargeConfigOut,
    name="pricing_template_surcharge_update",
)
def update_surcharge_config(
    config_id: int = Path(..., ge=1),
    payload: SurchargeConfigUpdateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    cfg = _load_config_or_404(db, config_id=config_id)
    _require_template_draft(db, int(cfg.template_id))

    data = payload.model_dump(exclude_unset=True)

    next_province_code = (
        _norm_nonempty(data["province_code"], "province_code")
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
            template_id=int(cfg.template_id),
            province_code=next_province_code,
        )
        if exists is not None and int(exists.id) != int(cfg.id):
            raise HTTPException(status_code=409, detail="Surcharge config for this province already exists")

    _validate_config_payload_for_write(
        province_mode=next_province_mode,
        fixed_amount=next_fixed_amount,
        cities_count=len(next_cities_payload),
    )

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
    return _to_surcharge_config_out(cfg)


@router.delete(
    "/surcharge-configs/{config_id}",
    status_code=status.HTTP_200_OK,
    name="pricing_template_surcharge_delete",
)
def delete_surcharge_config(
    config_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    cfg = db.get(ShippingProviderPricingTemplateSurchargeConfig, config_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Surcharge config not found")

    _require_template_draft(db, int(cfg.template_id))

    db.delete(cfg)
    db.commit()
    return {"ok": True}
