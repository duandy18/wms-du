# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_warehouses_schemas.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class SchemeWarehouseOut(BaseModel):
    warehouse_id: int
    active: bool


class SchemeWarehousesGetOut(BaseModel):
    ok: bool
    data: List[SchemeWarehouseOut]


class SchemeWarehousesPutIn(BaseModel):
    """
    全量替换：给定 scheme_id，写入其“起运适用仓库集合”。

    约定：
    - warehouses 允许空列表（表示该方案当前不适用于任何仓；会导致 Phase 3 推荐/算价候选集为空）
    - 不引入策略：仅表达事实绑定
    """
    warehouse_ids: List[int] = Field(default_factory=list)
    active: bool = True


class SchemeWarehousesPutOut(BaseModel):
    ok: bool
    data: List[SchemeWarehouseOut]
