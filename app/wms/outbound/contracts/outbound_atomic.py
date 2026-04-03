from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceType = Literal["direct", "upstream"]


class _Base(BaseModel):
    """
    WMS 原子出库 contracts 基类。

    设计原则：
    - 只表达 WMS 出库执行所必需的事实
    - 不把订单、店铺、平台、面单、包裹等上层履约语义直接耦合进核心合同
    - 上游来源通过 source_type / source_biz_type / source_ref 承载
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class OutboundAtomicReceiverIn(_Base):
    """
    原子出库收件信息。
    """

    name: Annotated[str, Field(min_length=1, max_length=100, description="收件人")]
    phone: Annotated[str | None, Field(default=None, max_length=50, description="联系电话")]

    province: Annotated[str, Field(min_length=1, max_length=100, description="省")]
    city: Annotated[str, Field(min_length=1, max_length=100, description="市")]
    district: Annotated[str | None, Field(default=None, max_length=100, description="区/县")]
    address: Annotated[str, Field(min_length=1, max_length=500, description="详细地址")]


class OutboundAtomicLineIn(_Base):
    """
    原子出库单行输入。

    识别原则：
    - item_id 与 barcode 至少提供一个
    """

    item_id: Annotated[int | None, Field(default=None, ge=1, description="商品 ID")]
    barcode: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="条码")]

    qty: Annotated[int, Field(gt=0, description="出库数量，必须为正整数")]

    @model_validator(mode="after")
    def validate_identity(self) -> "OutboundAtomicLineIn":
        if self.item_id is None and not self.barcode:
            raise ValueError("item_id or barcode is required")
        return self


class OutboundAtomicCreateIn(_Base):
    """
    原子出库创建输入。

    语义：
    - direct：由 WMS 直接发起，不依赖上游单据
    - upstream：由订单/调拨/外部任务映射而来
    """

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    source_type: Annotated[SourceType, Field(description="来源大类：direct / upstream")]
    source_biz_type: Annotated[str | None, Field(default=None, max_length=64, description="来源业务类型，如 sales_order / transfer")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源业务单号 / 外部引用号")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="备注")]

    receiver: OutboundAtomicReceiverIn
    lines: Annotated[list[OutboundAtomicLineIn], Field(min_length=1, description="出库行")]

    @model_validator(mode="after")
    def validate_source(self) -> "OutboundAtomicCreateIn":
        if self.source_type == "upstream" and not self.source_ref:
            raise ValueError("source_ref is required when source_type=upstream")
        return self


class OutboundAtomicLotAllocation(_Base):
    """
    原子出库 lot 分配结果。
    """

    lot_id: Annotated[int | None, Field(default=None, ge=1, description="lot_id")]
    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="lot_code")]
    qty: Annotated[int, Field(gt=0, description="该 lot 实际分配/扣减数量")]


class OutboundAtomicResultRow(_Base):
    """
    原子出库结果行。
    """

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    barcode: Annotated[str | None, Field(default=None, max_length=128, description="条码（回显）")]

    qty: Annotated[int, Field(gt=0, description="实际出库数量")]

    allocated_lots: list[OutboundAtomicLotAllocation] = Field(
        default_factory=list,
        description="实际分配/扣减的 lot 摘要",
    )


class OutboundAtomicCreateOut(_Base):
    """
    原子出库创建输出。
    """

    ok: bool = Field(default=True, description="是否成功")
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    source_type: Annotated[SourceType, Field(description="来源大类：direct / upstream")]
    source_biz_type: Annotated[str | None, Field(default=None, max_length=64, description="来源业务类型")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源业务单号 / 外部引用号")]

    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="执行链 trace_id")]

    rows: list[OutboundAtomicResultRow] = Field(default_factory=list, description="执行结果行")


__all__ = [
    "SourceType",
    "OutboundAtomicReceiverIn",
    "OutboundAtomicLineIn",
    "OutboundAtomicCreateIn",
    "OutboundAtomicLotAllocation",
    "OutboundAtomicResultRow",
    "OutboundAtomicCreateOut",
]
