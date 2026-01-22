# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_warehouses_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WarehouseLiteOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    active: bool


class SchemeWarehouseOut(BaseModel):
    scheme_id: int
    warehouse_id: int
    active: bool

    # ✅ 事实展示：带上仓库主数据（只读）
    warehouse: WarehouseLiteOut


class SchemeWarehousesGetOut(BaseModel):
    ok: bool
    data: List[SchemeWarehouseOut]


class SchemeWarehouseBindIn(BaseModel):
    """
    绑定单个起运仓（事实写入）。

    语义：
    - 绑定存在 = 具备“起运适用资格”
    - active=true = 该资格当前启用
    """
    warehouse_id: int = Field(..., ge=1)

    # ✅ 建议默认 false（避免“绑定即启用”的暗示）
    # 这里作为契约默认值；数据库层默认 true 不重要，因为我们插入会显式写 active。
    active: bool = False


class SchemeWarehouseBindOut(BaseModel):
    ok: bool
    data: SchemeWarehouseOut


class SchemeWarehousePatchIn(BaseModel):
    active: Optional[bool] = None


class SchemeWarehousePatchOut(BaseModel):
    ok: bool
    data: SchemeWarehouseOut


class SchemeWarehouseDeleteOut(BaseModel):
    ok: bool
    data: dict
