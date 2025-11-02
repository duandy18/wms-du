# app/schemas/outbound.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM / DTO 直接序列化
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名互填，便于未来演进
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 行项目 =========
class OutboundLine(_Base):
    """
    出库行项目（为保持兼容，item_id/location_id/qty 维持原义）
    - 新增可选字段不影响旧请求：sku / warehouse_id / ref_line / 批次提示
    - 服务层仍可按 FEFO 自动择批
    """
    item_id: Annotated[int, Field(ge=1, description="商品ID")]
    location_id: Annotated[int, Field(ge=1, description="出库库位ID")]
    qty: Annotated[int, Field(gt=0, description="出库数量（正整数）")]

    # 可选增强（不破兼容）
    sku: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    warehouse_id: Annotated[int | None, Field(default=None, ge=1)] = None
    ref_line: int | str | None = None

    # 可选批次提示（服务层可忽略而走 FEFO）
    batch_code: str | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_id": 1,
                "location_id": 101,
                "qty": 4,
                "sku": "CAT-FOOD-15KG",
                "warehouse_id": 1,
                "ref_line": 1,
                "batch_code": "B-20251028-A",
            }
        }
    }


# ========= 提交请求 =========
class OutboundCommitRequest(_Base):
    """
    出库提交（v1.0）
    - ref: 业务参考号（用于幂等）
    - lines: 至少 1 条
    - mode: NORMAL/FEFO（默认 FEFO 更贴近 WMS 逻辑）
    - allow_expired: 是否允许使用过期批次（默认 False）
    """
    ref: Annotated[str, Field(min_length=1, max_length=64)]
    lines: list[OutboundLine]
    mode: Literal["NORMAL", "FEFO"] = "FEFO"
    allow_expired: bool = False

    @field_validator("ref", mode="before")
    @classmethod
    def _trim_ref(cls, v: str) -> str:
        return v.strip()

    @field_validator("lines")
    @classmethod
    def _non_empty_lines(cls, v: list[OutboundLine]) -> list[OutboundLine]:
        if not v:
            raise ValueError("lines 不能为空")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "ref": "SO-202510-0001",
                "mode": "FEFO",
                "allow_expired": False,
                "lines": [
                    {"item_id": 1, "location_id": 101, "qty": 4, "ref_line": 1},
                    {"item_id": 1, "location_id": 102, "qty": 2, "ref_line": 2},
                ],
            }
        }
    }


# ========= 结果行 =========
class OutboundCommitResultLine(_Base):
    """
    单行提交结果
    - status: OK / IDEMPOTENT / INSUFFICIENT_STOCK
    - committed_qty: 实际提交数量（可能小于请求 qty）
    """
    item_id: int
    location_id: int
    committed_qty: int
    status: Literal["OK", "IDEMPOTENT", "INSUFFICIENT_STOCK"]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_id": 1,
                "location_id": 101,
                "committed_qty": 4,
                "status": "OK",
            }
        }
    }


# ========= 提交响应 =========
class OutboundCommitResponse(_Base):
    """
    提交响应（按 ref 汇总）
    """
    ref: str
    results: list[OutboundCommitResultLine]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "ref": "SO-202510-0001",
                "results": [
                    {"item_id": 1, "location_id": 101, "committed_qty": 4, "status": "OK"},
                    {"item_id": 1, "location_id": 102, "committed_qty": 2, "status": "OK"},
                ],
            }
        }
    }


__all__ = [
    "OutboundLine",
    "OutboundCommitRequest",
    "OutboundCommitResultLine",
    "OutboundCommitResponse",
]
