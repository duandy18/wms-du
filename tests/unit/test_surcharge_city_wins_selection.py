# tests/unit/test_surcharge_city_wins_selection.py
from __future__ import annotations

from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity
from app.services.shipping_quote.calc_quote_level3 import _select_surcharge_from_configs
from app.services.shipping_quote.types import Dest


def _cfg_province(
    *,
    id: int,
    scheme_id: int,
    province_code: str,
    province_name: str,
    amount: float,
    active: bool = True,
) -> ShippingProviderSurchargeConfig:
    cfg = ShippingProviderSurchargeConfig(
        id=id,
        scheme_id=scheme_id,
        province_code=province_code,
        province_name=province_name,
        province_mode="province",
        fixed_amount=amount,
        active=active,
    )
    cfg.cities = []
    return cfg


def _cfg_cities(
    *,
    id: int,
    scheme_id: int,
    province_code: str,
    province_name: str,
    cities: list[ShippingProviderSurchargeConfigCity],
    active: bool = True,
) -> ShippingProviderSurchargeConfig:
    cfg = ShippingProviderSurchargeConfig(
        id=id,
        scheme_id=scheme_id,
        province_code=province_code,
        province_name=province_name,
        province_mode="cities",
        fixed_amount=0,
        active=active,
    )
    cfg.cities = cities
    return cfg


def _city_row(
    *,
    id: int,
    config_id: int,
    city_code: str,
    city_name: str,
    amount: float,
    active: bool = True,
) -> ShippingProviderSurchargeConfigCity:
    return ShippingProviderSurchargeConfigCity(
        id=id,
        config_id=config_id,
        city_code=city_code,
        city_name=city_name,
        fixed_amount=amount,
        active=active,
    )


def test_select_surcharge_from_configs_hits_province_mode() -> None:
    dest = Dest(
        province="北京市",
        city="北京市",
        district="朝阳区",
        province_code="110000",
        city_code="110100",
    )
    reasons: list[str] = []

    cfg = _cfg_province(
        id=10,
        scheme_id=1,
        province_code="110000",
        province_name="北京市",
        amount=1.5,
    )

    chosen_cfg, chosen_city, amount, detail = _select_surcharge_from_configs(
        configs=[cfg],
        dest=dest,
        reasons=reasons,
    )

    assert chosen_cfg is not None
    assert chosen_cfg.id == 10
    assert chosen_city is None
    assert abs(amount - 1.5) < 1e-9
    assert detail == {"kind": "fixed", "amount": 1.5}
    assert any("surcharge_select: province>" in r for r in reasons)


def test_select_surcharge_from_configs_hits_city_mode() -> None:
    dest = Dest(
        province="广东省",
        city="深圳市",
        district="南山区",
        province_code="440000",
        city_code="440300",
    )
    reasons: list[str] = []

    city_sz = _city_row(
        id=101,
        config_id=20,
        city_code="440300",
        city_name="深圳市",
        amount=3.0,
    )
    city_gz = _city_row(
        id=102,
        config_id=20,
        city_code="440100",
        city_name="广州市",
        amount=2.0,
    )
    cfg = _cfg_cities(
        id=20,
        scheme_id=1,
        province_code="440000",
        province_name="广东省",
        cities=[city_sz, city_gz],
    )

    chosen_cfg, chosen_city, amount, detail = _select_surcharge_from_configs(
        configs=[cfg],
        dest=dest,
        reasons=reasons,
    )

    assert chosen_cfg is not None
    assert chosen_cfg.id == 20
    assert chosen_city is not None
    assert chosen_city.id == 101
    assert abs(amount - 3.0) < 1e-9
    assert detail == {"kind": "fixed", "amount": 3.0}
    assert any("surcharge_select: city>" in r for r in reasons)


def test_select_surcharge_from_configs_city_mode_miss_returns_zero() -> None:
    dest = Dest(
        province="广东省",
        city="东莞市",
        district=None,
        province_code="440000",
        city_code="441900",
    )
    reasons: list[str] = []

    city_sz = _city_row(
        id=201,
        config_id=30,
        city_code="440300",
        city_name="深圳市",
        amount=3.0,
    )
    cfg = _cfg_cities(
        id=30,
        scheme_id=1,
        province_code="440000",
        province_name="广东省",
        cities=[city_sz],
    )

    chosen_cfg, chosen_city, amount, detail = _select_surcharge_from_configs(
        configs=[cfg],
        dest=dest,
        reasons=reasons,
    )

    assert chosen_cfg is not None
    assert chosen_cfg.id == 30
    assert chosen_city is None
    assert abs(amount - 0.0) < 1e-9
    assert detail is None
    assert not any("surcharge_select:" in r for r in reasons)


def test_select_surcharge_from_configs_no_matching_province_returns_zero() -> None:
    dest = Dest(
        province="浙江省",
        city="杭州市",
        district=None,
        province_code="330000",
        city_code="330100",
    )
    reasons: list[str] = []

    cfg = _cfg_province(
        id=40,
        scheme_id=1,
        province_code="110000",
        province_name="北京市",
        amount=1.5,
    )

    chosen_cfg, chosen_city, amount, detail = _select_surcharge_from_configs(
        configs=[cfg],
        dest=dest,
        reasons=reasons,
    )

    assert chosen_cfg is None
    assert chosen_city is None
    assert abs(amount - 0.0) < 1e-9
    assert detail is None
    assert reasons == []


def test_select_surcharge_from_configs_skips_inactive_config_and_city() -> None:
    dest = Dest(
        province="广东省",
        city="深圳市",
        district=None,
        province_code="440000",
        city_code="440300",
    )
    reasons: list[str] = []

    inactive_city = _city_row(
        id=301,
        config_id=50,
        city_code="440300",
        city_name="深圳市",
        amount=5.0,
        active=False,
    )
    inactive_cfg = _cfg_cities(
        id=50,
        scheme_id=1,
        province_code="440000",
        province_name="广东省",
        cities=[inactive_city],
        active=True,
    )
    disabled_cfg = _cfg_province(
        id=51,
        scheme_id=1,
        province_code="440000",
        province_name="广东省",
        amount=8.0,
        active=False,
    )

    chosen_cfg, chosen_city, amount, detail = _select_surcharge_from_configs(
        configs=[inactive_cfg, disabled_cfg],
        dest=dest,
        reasons=reasons,
    )

    assert chosen_cfg is not None
    assert chosen_cfg.id == 50
    assert chosen_city is None
    assert abs(amount - 0.0) < 1e-9
    assert detail is None
    assert not any("surcharge_select:" in r for r in reasons)
