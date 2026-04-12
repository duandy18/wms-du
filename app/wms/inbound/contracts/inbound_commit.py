# app/wms/inbound/contracts/inbound_commit.py
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


InboundSourceType = Literal[
    "PURCHASE_ORDER",
    "MANUAL",
    "RETURN",
    "TRANSFER_IN",
    "ADJUST_IN",
]


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundCommitLineIn(_Base):
    """
    一层式入库提交行输入。

    设计原则：
    - 输入只接用户事实：商品/条码、包装单位、输入数量、批号/日期
    - 不接 qty_base，qty_base 由后端根据 PMS item_uoms.ratio_to_base 计算
    - 采购来源时允许显式带 po_line_id；其他来源不需要 source_line_ref 这种泛字段
    """

    item_id: Annotated[int | None, Field(default=None, ge=1, description="商品 ID")]
    barcode: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="条码")]

    uom_id: Annotated[int | None, Field(default=None, ge=1, description="包装单位 ID")]
    qty_input: Annotated[int, Field(gt=0, description="输入数量，按 uom_id 口径")]

    lot_code_input: Annotated[str | None, Field(default=None, max_length=128, description="业务批号/生产批号输入")]
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")

    po_line_id: Annotated[int | None, Field(default=None, ge=1, description="采购来源时的采购单行 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=255, description="行备注")]

    @model_validator(mode="after")
    def validate_identity(self) -> "InboundCommitLineIn":
        if self.item_id is None and not self.barcode:
            raise ValueError("item_id or barcode is required")
        return self

    @model_validator(mode="after")
    def validate_uom_input(self) -> "InboundCommitLineIn":
        # 手动输入时必须明确包装单位；扫码场景可由后端通过 barcode 反解补齐
        if self.uom_id is None and not self.barcode:
            raise ValueError("uom_id is required when barcode is not provided")
        return self

    @model_validator(mode="after")
    def validate_dates(self) -> "InboundCommitLineIn":
        if self.production_date and self.expiry_date and self.production_date > self.expiry_date:
            raise ValueError("production_date cannot be later than expiry_date")
        return self


class InboundCommitIn(_Base):
    """
    一层式入库提交输入。

    说明：
    - source_type 直接表达业务来源，不再暴露 source_biz_type
    - source_ref 为来源单号/引用号，可空（手工入库时允许为空）
    - occurred_at 为业务发生时间，必须真正传到库存/台账，不允许被服务内部 now() 覆盖
    """

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: Annotated[InboundSourceType, Field(description="入库来源类型")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(..., description="业务发生时间")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="整单备注")]

    lines: Annotated[list[InboundCommitLineIn], Field(min_length=1, description="提交行")]


class InboundCommitResultRow(_Base):
    """
    提交后回显的结果行。

    说明：
    - 返回后端实际解析后的 item/uom/qty 快照
    - qty_base / ratio_to_base_snapshot 是交易快照，不是主数据真相
    """

    line_no: Annotated[int, Field(ge=1, description="事件内行号")]
    item_id: Annotated[int, Field(ge=1, description="实际解析商品 ID")]
    uom_id: Annotated[int, Field(ge=1, description="实际解析包装单位 ID")]

    qty_input: Annotated[int, Field(gt=0, description="输入数量")]
    ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="提交时冻结的换算倍率")]
    qty_base: Annotated[int, Field(gt=0, description="提交时冻结的 base 数量")]

    lot_id: Annotated[int | None, Field(default=None, ge=1, description="实际落账 lot_id")]
    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="实际落账 lot_code")]

    po_line_id: Annotated[int | None, Field(default=None, ge=1, description="采购来源时的采购单行 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=255, description="行备注")]


class InboundCommitOut(_Base):
    """
    一层式入库提交输出。

    说明：
    - event_id：业务事件锚点，用于查询/冲销/更正
    - trace_id：技术链路锚点，用于日志/台账链路追踪
    """

    ok: bool = Field(default=True, description="是否成功")

    event_id: Annotated[int, Field(ge=1, description="入库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="入库事件单号")]
    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="技术链路追踪号")]

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: Annotated[InboundSourceType, Field(description="入库来源类型")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(..., description="业务发生时间")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="整单备注")]

    rows: list[InboundCommitResultRow] = Field(default_factory=list, description="结果行")


__all__ = [
    "InboundSourceType",
    "InboundCommitLineIn",
    "InboundCommitIn",
    "InboundCommitResultRow",
    "InboundCommitOut",
]
