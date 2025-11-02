from __future__ import annotations
from datetime import date, timedelta

class ExpiryError(ValueError):
    pass

def calc_expire_at(
    production_date: date | None,
    shelf_life_days: int | None,
    allow_null: bool = True,
) -> date | None:
    """
    统一口径：
    - 若 production_date 与 shelf_life_days 同时提供：expire_at = production_date + days
    - 若两者都为 None：返回 None（非保质品）；若 allow_null=False 则抛错
    - 若只提供其一：抛 ExpiryError（口径不完整）
    - 禁止负天数；返回“日期”（无时间分量）
    """
    if production_date is None and shelf_life_days is None:
        if allow_null:
            return None
        raise ExpiryError("expire_at requires production_date and shelf_life_days")
    if production_date is None or shelf_life_days is None:
        raise ExpiryError("both production_date and shelf_life_days are required")
    if shelf_life_days < 0:
        raise ExpiryError("shelf_life_days must be >= 0")
    return production_date + timedelta(days=int(shelf_life_days))
