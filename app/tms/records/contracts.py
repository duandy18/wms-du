# app/tms/records/contracts.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读合同；
# - 仅暴露 shipping_records 当前“发货事实台帐”语义下的字段；
# - 不暴露物流状态、不暴露对账结果字段。
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShippingRecordOut(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str

    warehouse_id: int | None = Field(default=None)
    shipping_provider_id: int | None = Field(default=None)

    carrier_code: str | None = None
    carrier_name: str | None = None
    tracking_no: str | None = None

    gross_weight_kg: float | None = None
    cost_estimated: float | None = None

    dest_province: str | None = None
    dest_city: str | None = None

    created_at: datetime
