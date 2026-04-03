from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceType = Literal["direct", "upstream"]


class _Base(BaseModel):
    """
    WMS 原子入库 contracts 基类。

    设计原则：
    - 只表达 WMS 入库执行所必需的事实
    - 不把采购单、供应商、收货单等上游业务对象直接耦合进核心合同
    - 上游来源通过 source_type / source_biz_type / source_ref 承载
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundAtomicLineIn(_Base):
    """
    原子入库单行输入。

    识别原则：
    - item_id 与 barcode 至少提供一个
    - 商品名称不作为核心合同主识别键，只适合作为前端搜索辅助
    """

    item_id: Annotated[int | None, Field(default=None, ge=1, description="商品 ID")]
    barcode: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="条码")]

    qty: Annotated[int, Field(gt=0, description="入库数量，必须为正整数")]
    ref_line: Annotated[int | None, Field(default=None, ge=1, description="来源 ref 内顺序号（可选）")]

    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="批次码 / lot_code（可选）")]
    production_date: date | None = Field(default=None, description="生产日期（可选）")
    expiry_date: date | None = Field(default=None, description="到期日期（可选）")

    @model_validator(mode="after")
    def validate_identity(self) -> "InboundAtomicLineIn":
        if self.item_id is None and not self.barcode:
            raise ValueError("item_id or barcode is required")
        return self

    @model_validator(mode="after")
    def validate_dates(self) -> "InboundAtomicLineIn":
        if self.production_date and self.expiry_date and self.production_date > self.expiry_date:
            raise ValueError("production_date cannot be later than expiry_date")
        return self


class InboundAtomicCreateIn(_Base):
    """
    原子入库创建输入。

    语义：
    - direct：由 WMS 直接发起，不依赖上游单据
    - upstream：由采购/退货/调拨/其他外部单据映射而来
    """

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    source_type: Annotated[SourceType, Field(description="来源大类：direct / upstream")]
    source_biz_type: Annotated[str | None, Field(default=None, max_length=64, description="来源业务类型，如 purchase / return / transfer")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源业务单号 / 外部引用号")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="备注")]

    lines: Annotated[list[InboundAtomicLineIn], Field(min_length=1, description="入库行")]

    @model_validator(mode="after")
    def validate_source(self) -> "InboundAtomicCreateIn":
        if self.source_type == "upstream" and not self.source_ref:
            raise ValueError("source_ref is required when source_type=upstream")
        return self


class InboundAtomicResultRow(_Base):
    """
    原子入库结果行。

    说明：
    - lot_id / lot_code 为实际落账结果
    - barcode 为可选回显字段，便于前端展示
    """

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    barcode: Annotated[str | None, Field(default=None, max_length=128, description="条码（回显）")]

    qty: Annotated[int, Field(gt=0, description="实际入库数量")]

    lot_id: Annotated[int | None, Field(default=None, ge=1, description="实际落账 lot_id")]
    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="实际落账 lot_code")]


class InboundAtomicCreateOut(_Base):
    """
    原子入库创建输出。
    """

    ok: bool = Field(default=True, description="是否成功")
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    source_type: Annotated[SourceType, Field(description="来源大类：direct / upstream")]
    source_biz_type: Annotated[str | None, Field(default=None, max_length=64, description="来源业务类型")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源业务单号 / 外部引用号")]

    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="执行链 trace_id")]

    rows: list[InboundAtomicResultRow] = Field(default_factory=list, description="执行结果行")


__all__ = [
    "SourceType",
    "InboundAtomicLineIn",
    "InboundAtomicCreateIn",
    "InboundAtomicResultRow",
    "InboundAtomicCreateOut",
]
