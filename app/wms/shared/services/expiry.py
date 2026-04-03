from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


class ExpiryError(ValueError):
    pass


_ALLOWED_UNITS = {"DAY", "WEEK", "MONTH", "YEAR"}


def calc_expire_at(
    production_date: date | None,
    shelf_life_value: int | None,
    shelf_life_unit: str | None,
    allow_null: bool = True,
) -> date | None:
    """
    统一口径（v2：value + unit）：

    - 若 production_date 与 shelf_life_value/unit 同时提供：
        expire_at = production_date + duration(value, unit)
    - 若三者都为 None：返回 None（非保质品）；若 allow_null=False 则抛错
    - 若缺任意一项：抛 ExpiryError（口径不完整）
    - value 必须为正数；unit 必须在 DAY/WEEK/MONTH/YEAR 中

    说明：
    - 旧口径 shelf_life_days 已废弃，调用方应改用 shelf_life_value + shelf_life_unit。
    """
    if production_date is None and shelf_life_value is None and shelf_life_unit is None:
        if allow_null:
            return None
        raise ExpiryError("expire_at requires production_date and shelf_life_value/unit")

    if production_date is None or shelf_life_value is None or shelf_life_unit is None:
        raise ExpiryError("production_date, shelf_life_value and shelf_life_unit are required together")

    try:
        v = int(shelf_life_value)
    except Exception as e:
        raise ExpiryError(f"invalid shelf_life_value: {shelf_life_value!r}") from e

    if v <= 0:
        raise ExpiryError("shelf_life_value must be > 0")

    u = str(shelf_life_unit).strip().upper()
    if u not in _ALLOWED_UNITS:
        raise ExpiryError(f"shelf_life_unit must be one of {_ALLOWED_UNITS}, got {shelf_life_unit!r}")

    if u == "DAY":
        return production_date + timedelta(days=v)
    if u == "WEEK":
        return production_date + timedelta(days=7 * v)
    if u == "MONTH":
        return production_date + relativedelta(months=v)
    # u == "YEAR"
    return production_date + relativedelta(years=v)
