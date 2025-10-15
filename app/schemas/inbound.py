# app/schemas/inbound.py
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel
from pydantic.config import ConfigDict

# ---------- 入库（/inbound/receive） ----------


class ReceiveIn(BaseModel):
    """入库请求体：按 SKU 入库到 STAGE。"""

    sku: str
    qty: int
    ref: str
    ref_line: int | str

    # 可选批次信息（当前服务未强校验，仅透传/保留接口兼容）
    batch_code: str | None = None
    production_date: date | None = None
    expiry_date: date | None = None

    # 可选发生时间（当前 DB 台账未落 ts 列，但保留兼容字段）
    occurred_at: datetime | None = None

    # v2 配置：容忍多余字段、允许 ORM 对象
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ReceiveOut(BaseModel):
    """入库结果：返回 item_id 与实际入库数量；idempotent 可选（用于 quick 测试断言）。"""

    item_id: int
    accepted_qty: int
    idempotent: bool | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# ---------- Putaway（/inbound/putaway） ----------


class PutawayIn(BaseModel):
    """上架/搬运请求体：从 STAGE 搬到目标库位。"""

    sku: str
    qty: int
    to_location_id: int
    ref: str
    ref_line: int | str

    # 可选：若未来按批次搬运，保留 batch_code 兼容位
    batch_code: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


__all__ = ["ReceiveIn", "ReceiveOut", "PutawayIn"]
