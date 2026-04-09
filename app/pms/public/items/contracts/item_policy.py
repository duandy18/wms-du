# app/pms/public/items/contracts/item_policy.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


ShelfLifeUnit = Literal["DAY", "WEEK", "MONTH", "YEAR"]
ExpiryPolicy = Literal["NONE", "REQUIRED"]
LotSourcePolicy = Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"]


class ItemPolicy(_Base):
    """
    PMS 对外规则读模型。

    给 WMS / procurement / 其他执行域读取：
    - 有效期规则
    - 批次来源策略
    - 单位治理策略
    """

    item_id: Annotated[int, Field(gt=0)]

    expiry_policy: ExpiryPolicy
    shelf_life_value: Annotated[int | None, Field(default=None, gt=0)] = None
    shelf_life_unit: ShelfLifeUnit | None = None

    lot_source_policy: LotSourcePolicy
    derivation_allowed: bool
    uom_governance_enabled: bool
