# app/schemas/return_task.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReturnTaskLineBase(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    expected_qty: Optional[int] = Field(
        None,
        description="计划退货数量（来自采购单或人工录入）",
    )


class ReturnTaskLineCreate(ReturnTaskLineBase):
    po_line_id: Optional[int] = Field(
        None,
        description="关联采购单行 ID（可选）",
    )
    item_name: Optional[str] = Field(
        None,
        description="商品名称快照（可选）",
    )
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选）",
    )


class ReturnTaskLineOut(BaseModel):
    id: int
    task_id: int

    po_line_id: Optional[int]
    item_id: int
    item_name: Optional[str]
    batch_code: Optional[str]

    expected_qty: Optional[int]
    picked_qty: int
    committed_qty: Optional[int]

    status: str
    remark: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReturnTaskCreateFromPo(BaseModel):
    warehouse_id: Optional[int] = Field(
        None,
        description="退货仓库 ID；不传则默认用采购单上的 warehouse_id",
    )
    include_zero_received: bool = Field(
        False,
        description="是否包含未收货的行（通常不需要）",
    )


class ReturnTaskPickIn(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., description="本次退货拣出数量（可正可负）")
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选）",
    )


class ReturnTaskCommitIn(BaseModel):
    trace_id: Optional[str] = Field(
        None,
        description="用于跨表追踪的 trace_id，可选",
    )


class ReturnTaskOut(BaseModel):
    id: int
    po_id: Optional[int]
    supplier_id: Optional[int]
    supplier_name: Optional[str]
    warehouse_id: int
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    lines: List[ReturnTaskLineOut] = []

    model_config = ConfigDict(from_attributes=True)
