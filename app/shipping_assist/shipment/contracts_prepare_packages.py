# app/shipping_assist/shipment/contracts_prepare_packages.py
# 分拆说明：
# - 本文件从 contracts_prepare.py 中拆出“发运准备-包裹基础事实”相关合同。
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ShipPreparePackageOut(BaseModel):
    package_no: int
    weight_kg: Optional[float] = None
    warehouse_id: Optional[int] = None
    pricing_status: str
    selected_provider_id: Optional[int] = None


class ShipPreparePackagesResponse(BaseModel):
    ok: bool = True
    items: List[ShipPreparePackageOut] = Field(default_factory=list)


class ShipPreparePackageCreateResponse(BaseModel):
    ok: bool = True
    item: ShipPreparePackageOut


class ShipPreparePackageUpdateRequest(BaseModel):
    weight_kg: Optional[float] = Field(default=None, gt=0)
    warehouse_id: Optional[int] = Field(default=None, ge=1)


class ShipPreparePackageUpdateResponse(BaseModel):
    ok: bool = True
    item: ShipPreparePackageOut
