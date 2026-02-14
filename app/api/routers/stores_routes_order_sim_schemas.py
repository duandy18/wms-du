# app/api/routers/stores_routes_order_sim_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, conint


OrderSimRowNo = conint(ge=1, le=6)


class MerchantLineItemIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_no: OrderSimRowNo
    filled_code: Optional[str] = None
    title: Optional[str] = None
    spec: Optional[str] = None
    if_version: Optional[int] = Field(None, description="可选乐观锁版本；不传则强制覆盖")


class OrderSimMerchantLinesPutIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[MerchantLineItemIn] = Field(default_factory=list)


class MerchantLineItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_no: int
    filled_code: Optional[str] = None
    title: Optional[str] = None
    spec: Optional[str] = None
    version: int = 0
    updated_at: Optional[Any] = None


class OrderSimMerchantLinesGetOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: Dict[str, Any]


class OrderSimMerchantLinesPutOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: Dict[str, Any]


class CartLineItemIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_no: OrderSimRowNo
    checked: bool = False
    qty: int = 0

    # ✅ 地址字段（与 OrderService.ingest(address=...) 对齐）
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    zipcode: Optional[str] = None

    if_version: Optional[int] = None


class OrderSimCartPutIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[CartLineItemIn] = Field(default_factory=list)


class CartLineItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row_no: int
    checked: bool = False
    qty: int = 0

    # ✅ 地址字段（与 ingest 对齐）
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    zipcode: Optional[str] = None

    version: int = 0
    updated_at: Optional[Any] = None


class OrderSimCartGetOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: Dict[str, Any]


class OrderSimCartPutOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: Dict[str, Any]


class OrderSimGenerateOrderIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    idempotency_key: Optional[str] = Field(None, description="可选：用于 ext_order_no 幂等锚点（同 key → 同 ext_order_no）")


class OrderSimGenerateOrderOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: Dict[str, Any]


# ============================================================
# ✅ 新增：filled_code 下拉候选（只用绑定事实 merchant_code → published FSKU）
# ============================================================

class OrderSimFilledCodeOptionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    filled_code: str = Field(..., min_length=1, max_length=128, description="商家后台填写码（merchant_code / filled_code）")
    suggested_title: str = Field(..., description="下拉选中后默认带出的标题（可编辑）")
    components_summary: str = Field(..., description="FSKU components 摘要（spec 只读展示，不参与解析）")


class OrderSimFilledCodeOptionsData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[OrderSimFilledCodeOptionOut] = Field(default_factory=list)


class OrderSimFilledCodeOptionsOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool
    data: OrderSimFilledCodeOptionsData
