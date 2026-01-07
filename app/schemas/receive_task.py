# app/schemas/receive_task.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReceiveTaskLineBase(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    expected_qty: Optional[int] = Field(
        None,
        description="应收数量（可选，来自采购单/订单或人工录入）",
    )


class ReceiveTaskLineCreate(ReceiveTaskLineBase):
    po_line_id: Optional[int] = Field(
        None,
        description="关联采购单行 ID（可选）",
    )
    item_name: Optional[str] = Field(
        None,
        description="商品名称快照（可选）",
    )
    item_sku: Optional[str] = Field(None, description="商品 SKU 快照（可选）")
    category: Optional[str] = Field(None, description="业务分组（猫条/鲜封包等）")
    spec_text: Optional[str] = Field(None, description="规格描述，如 85g*12袋")
    base_uom: Optional[str] = Field(None, description="基础单位，如 袋/包/罐")
    purchase_uom: Optional[str] = Field(None, description="采购单位，如 件/箱")
    units_per_case: Optional[int] = Field(None, description="每件包含的基础单位数量（可选）")

    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选）",
    )
    production_date: Optional[date] = Field(
        None,
        description="生产日期（可选）",
    )
    expiry_date: Optional[date] = Field(
        None,
        description="到期日期（可选）",
    )


class ReceiveTaskLineOut(BaseModel):
    id: int
    task_id: int

    po_line_id: Optional[int]

    # 采购行快照
    item_id: int
    item_name: Optional[str]
    item_sku: Optional[str]
    category: Optional[str]
    spec_text: Optional[str]
    base_uom: Optional[str]
    purchase_uom: Optional[str]
    units_per_case: Optional[int]

    # 批次 + 日期
    batch_code: Optional[str]
    production_date: Optional[date]
    expiry_date: Optional[date]

    # 数量
    expected_qty: Optional[int]
    scanned_qty: int
    committed_qty: Optional[int]

    status: str
    remark: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReceiveTaskCreateFromPo(BaseModel):
    """
    从采购单创建收货任务的请求体
    """

    warehouse_id: Optional[int] = Field(
        None,
        description="收货仓库 ID；不传则默认用采购单上的 warehouse_id",
    )
    include_fully_received: bool = Field(
        False,
        description="是否包含已收完的行（通常不需要）",
    )


class ReceiveTaskCreateFromPoSelectedLineIn(BaseModel):
    """
    选择式创建：本次到货的某一行
    """

    po_line_id: int = Field(..., description="采购单行 ID（必须属于该采购单）")
    qty_planned: int = Field(..., gt=0, description="本次计划收货量（>0，且不超过剩余应收）")


class ReceiveTaskCreateFromPoSelected(BaseModel):
    """
    从采购单“选择部分行”创建收货任务（本次到货批次）
    """

    warehouse_id: Optional[int] = Field(
        None,
        description="收货仓库 ID；不传则默认用采购单上的 warehouse_id",
    )
    lines: List[ReceiveTaskCreateFromPoSelectedLineIn] = Field(
        ...,
        description="本次到货行清单（至少一行）",
    )

    @field_validator("lines")
    @classmethod
    def _lines_non_empty_and_unique(cls, v: List[ReceiveTaskCreateFromPoSelectedLineIn]):
        if not v:
            raise ValueError("lines 不能为空")
        seen: set[int] = set()
        for ln in v:
            if ln.po_line_id in seen:
                raise ValueError(f"lines 中存在重复 po_line_id={ln.po_line_id}")
            seen.add(ln.po_line_id)
        return v


class OrderReturnLineIn(BaseModel):
    """
    客户退货行（from-order 用）
    """

    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., gt=0, description="本次计划退回数量（>0）")

    item_name: Optional[str] = Field(None, description="商品名称快照（可选）")
    batch_code: Optional[str] = Field(None, description="批次编码（可选）")


class ReceiveTaskCreateFromOrder(BaseModel):
    """
    从订单创建收货任务的请求体（客户退货入库 / RMA 模式）
    """

    warehouse_id: Optional[int] = Field(
        None,
        description="收货仓库 ID；若不传则使用默认仓或由服务层约定",
    )
    lines: List[OrderReturnLineIn] = Field(
        ...,
        description="客户退货行列表，至少一行",
    )

    @field_validator("lines")
    @classmethod
    def _lines_non_empty(cls, v: List[OrderReturnLineIn]):
        if not v:
            raise ValueError("退货行不能为空")
        return v


class ReceiveTaskScanIn(BaseModel):
    """
    收货任务的扫码 / 实收录入请求：

    - item_id: 商品 ID
    - qty: 本次扫码/录入的数量（可正可负，允许回退）
    - batch_code: 批次编码（可选）
    - production_date / expiry_date: 批次日期（可选）
    """

    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., description="本次录入数量，可正可负")
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（可选）",
    )
    production_date: Optional[date] = Field(
        None,
        description="生产日期（可选）",
    )
    expiry_date: Optional[date] = Field(
        None,
        description="到期日期（可选）",
    )


class ReceiveTaskCommitIn(BaseModel):
    """
    收货任务 commit 请求体
    """

    trace_id: Optional[str] = Field(
        None,
        description="用于跨表追踪的 trace_id，可选",
    )


class ReceiveTaskOut(BaseModel):
    id: int

    source_type: str
    source_id: Optional[int]

    po_id: Optional[int]
    supplier_id: Optional[int]
    supplier_name: Optional[str]
    warehouse_id: int
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    lines: List[ReceiveTaskLineOut] = []

    model_config = ConfigDict(from_attributes=True)
