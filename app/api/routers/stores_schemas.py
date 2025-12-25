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
    # 创建时是否允许传 email/联系人/电话，看你需求，这里先不暴露：
    # email: Optional[constr(max_length=255)] = None
    # contact_name: Optional[constr(max_length=100)] = None
    # contact_phone: Optional[constr(max_length=50)] = None


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

    # 新增主数据字段
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

    # 新增：可更新 email / 联系人 / 电话
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
    """
    店铺平台授权状态返回：

    data:
      - store_id
      - platform
      - shop_id
      - auth_source: "NONE" / "MANUAL" / "OAUTH"
      - expires_at: ISO 字符串或 null
      - mall_id: 平台侧店铺 ID（如 PDD mall_id），可能为 null
    """

    ok: bool = True
    data: Dict[str, Any]
