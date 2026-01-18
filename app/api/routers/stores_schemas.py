# app/api/routers/stores_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, constr

# ---------- Pydantic I/O ----------

PlatformStr = constr(min_length=2, max_length=32)


class StoreCreateIn(BaseModel):
    platform: PlatformStr
    shop_id: constr(min_length=1, max_length=128)
    name: Optional[constr(min_length=1, max_length=256)] = None


class StoreCreateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindWarehouseIn(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    is_default: bool = False
    priority: int = Field(100, ge=0, le=100_000)
    # 若不传 is_top，由后端按 is_default 推导
    is_top: Optional[bool] = Field(
        default=None,
        description="是否主仓；若为 null，由后端按 is_default 推导",
    )


class BindWarehouseOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class DefaultWarehouseOut(BaseModel):
    ok: bool = True
    data: Dict[str, Optional[int]]


class StoreDetailOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class StoreListItem(BaseModel):
    id: int
    platform: str
    shop_id: str
    name: str
    active: bool
    route_mode: str

    email: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


class StoreListOut(BaseModel):
    ok: bool = True
    data: List[StoreListItem]


class StoreUpdateIn(BaseModel):
    name: Optional[constr(min_length=1, max_length=256)] = None
    active: Optional[bool] = None
    route_mode: Optional[constr(min_length=1, max_length=32)] = None

    email: Optional[constr(max_length=255)] = None
    contact_name: Optional[constr(max_length=100)] = None
    contact_phone: Optional[constr(max_length=50)] = None


class StoreUpdateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindingUpdateIn(BaseModel):
    is_default: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=100_000)
    is_top: Optional[bool] = None


class BindingUpdateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindingDeleteOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class StorePlatformAuthOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


# ================================
# 店铺 SKU（store_items）
# ================================

class StoreItemRow(BaseModel):
    item_id: int = Field(..., ge=1)
    item_name: Optional[str] = None
    platform_sku: Optional[str] = None  # 预留：将来对接平台 SKU


class StoreItemsListOut(BaseModel):
    ok: bool = True
    data: List[StoreItemRow]


class StoreItemAddIn(BaseModel):
    item_id: int = Field(..., ge=1)


class StoreItemAddOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class StoreItemDeleteOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


# ================================
# 省级路由表（Province Routing）
# ================================

class ProvinceRouteItem(BaseModel):
    id: int
    store_id: int
    province: str

    warehouse_id: int
    warehouse_name: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_active: bool = True

    priority: int = 100
    active: bool = True


class ProvinceRouteListOut(BaseModel):
    ok: bool = True
    data: List[ProvinceRouteItem]


class ProvinceRouteCreateIn(BaseModel):
    province: constr(min_length=1, max_length=32)
    warehouse_id: int = Field(..., ge=1)
    priority: int = Field(100, ge=0, le=100_000)
    active: bool = True


class ProvinceRouteUpdateIn(BaseModel):
    province: Optional[constr(min_length=1, max_length=32)] = None
    warehouse_id: Optional[int] = Field(default=None, ge=1)
    priority: Optional[int] = Field(default=None, ge=0, le=100_000)
    active: Optional[bool] = None


class ProvinceRouteWriteOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class RoutingHealthOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]
