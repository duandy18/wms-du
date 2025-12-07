# app/schemas/inbound.py
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


# 统一：允许 ORM 对象、忽略多余字段、支持字段名/别名互填（便于兼容旧客户端）
class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ---------- 入库（/inbound/receive） ----------

SKU = Annotated[str, Field(min_length=1, max_length=128, description="商品 SKU")]


class ReceiveIn(_Base):
    """
    入库请求体（v1.0）
    - 以 SKU 为主键进行入库；默认由服务层决定落地库位（例如收货暂存位）。
    - 幂等建议：服务层以 (ref, ref_line, sku, qty) 判定。
    """

    sku: SKU
    qty: Annotated[int, Field(gt=0, description="入库数量（正整数）")]
    ref: Annotated[
        str, Field(min_length=1, max_length=128, description="业务参考号：采购单/入库单等")
    ]
    ref_line: int | str

    # 可选批次信息（保持接口兼容，服务层可透传/轻度校验）
    batch_code: str | None = Field(default=None, description="批次编码（可选）")
    production_date: date | None = Field(default=None, description="生产日期（可选）")
    expiry_date: date | None = Field(default=None, description="到期日期（可选）")

    # 可选发生时间（当前 DB 台账可能未落 ts 列，但保留兼容字段）
    occurred_at: datetime | None = Field(default=None, description="业务发生时间（可选）")

    # 文档示例（FastAPI 会带到 Swagger）
    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "sku": "CAT-FOOD-15KG",
                "qty": 10,
                "ref": "PO-202510-0001",
                "ref_line": 1,
                "batch_code": "B-20251028-A",
                "production_date": "2025-10-01",
                "expiry_date": "2026-04-01",
                "occurred_at": "2025-10-28T10:00:00Z",
            }
        }
    }


class ReceiveOut(_Base):
    """
    入库结果（v1.0）
    - item_id：服务层解析得到的内部商品ID
    - accepted_qty：实际入库数量（可能与请求 qty 相同或经业务校正）
    - idempotent：若命中幂等，返回 True 便于 quick/smoke 断言
    """

    item_id: int
    accepted_qty: int
    idempotent: bool | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"item_id": 1, "accepted_qty": 10, "idempotent": False}}
    }


# ---------- Putaway（/inbound/putaway） ----------
class PutawayIn(_Base):
    """
    上架/搬运请求体（v1.0）
    - 常见流程：从收货暂存位搬至目标库位（服务层做 FEFO/约束检查）
    - 若未来需要“按批次搬运”，可启用 batch_code 字段
    """

    sku: SKU
    qty: Annotated[int, Field(gt=0, description="搬运数量（正整数）")]
    to_location_id: Annotated[int, Field(gt=0, description="目标库位 ID")]
    ref: Annotated[str, Field(min_length=1, max_length=128, description="业务参考号")]
    ref_line: int | str

    # 预留批次字段（可选）
    batch_code: str | None = Field(default=None, description="批次编码（可选）")

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "sku": "CAT-FOOD-15KG",
                "qty": 5,
                "to_location_id": 102,
                "ref": "PUT-202510-0001",
                "ref_line": 2,
                "batch_code": "B-20251028-A",
            }
        }
    }


__all__ = ["ReceiveIn", "ReceiveOut", "PutawayIn"]
