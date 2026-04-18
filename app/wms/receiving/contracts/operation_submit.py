from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundOperationEntryIn(_Base):
    qty_inbound: Annotated[Decimal, Field(gt=0, description="本次收货数量（按实际包装）")]
    barcode_input: Annotated[
        str | None,
        Field(default=None, max_length=128, description="扫码原始条码（可选）"),
    ]
    actual_item_uom_id: Annotated[
        int | None,
        Field(default=None, ge=1, description="实际收货包装单位 ID（可选；扫码时可由条码反解）"),
    ]
    batch_no: Annotated[str | None, Field(default=None, max_length=128, description="批次号")]
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="批次子行备注")]

    @model_validator(mode="after")
    def validate_dates(self) -> "InboundOperationEntryIn":
        if (
            self.production_date is not None
            and self.expiry_date is not None
            and self.production_date > self.expiry_date
        ):
            raise ValueError("production_date cannot be later than expiry_date")
        return self


class InboundOperationLineIn(_Base):
    receipt_line_no: Annotated[int, Field(ge=1, description="任务行号")]
    entries: Annotated[list[InboundOperationEntryIn], Field(min_length=1, description="本次实际收货子行")]


class InboundOperationSubmitIn(_Base):
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="本次整单备注")]
    lines: Annotated[list[InboundOperationLineIn], Field(min_length=1, description="本次收货行")]

    @model_validator(mode="after")
    def validate_unique_receipt_line_no(self) -> "InboundOperationSubmitIn":
        seen: set[int] = set()
        for line in self.lines:
            if line.receipt_line_no in seen:
                raise ValueError(f"duplicate receipt_line_no: {line.receipt_line_no}")
            seen.add(line.receipt_line_no)
        return self


class InboundOperationLineOut(_Base):
    id: Annotated[int, Field(ge=1, description="操作事实行 ID")]
    receipt_line_no_snapshot: Annotated[int, Field(ge=1, description="任务行号快照")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="商品名快照")]
    item_spec_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="规格快照")]
    actual_item_uom_id: Annotated[int, Field(ge=1, description="实际包装单位 ID")]
    actual_uom_name_snapshot: Annotated[str | None, Field(default=None, max_length=64, description="实际单位名快照")]
    actual_ratio_to_base_snapshot: Annotated[Decimal, Field(gt=0, description="实际倍率快照")]
    actual_qty_input: Annotated[Decimal, Field(gt=0, description="本次实际包装数量")]
    qty_base: Annotated[Decimal, Field(gt=0, description="折算 base 数量")]
    batch_no: Annotated[str | None, Field(default=None, max_length=128, description="批次号")]
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")
    lot_id: Annotated[int | None, Field(default=None, ge=1, description="系统 lot_id")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="行备注")]


class InboundOperationSubmitOut(_Base):
    id: Annotated[int, Field(ge=1, description="操作事实头 ID")]
    receipt_no_snapshot: Annotated[str, Field(min_length=1, max_length=64, description="任务号快照")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="仓库名快照")]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    supplier_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="供应商名快照")]
    operator_id: Annotated[int | None, Field(default=None, ge=1, description="操作人 ID")]
    operator_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="操作人名快照")]
    operated_at: datetime = Field(description="操作时间")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="整单备注")]
    lines: list[InboundOperationLineOut] = Field(default_factory=list, description="操作事实行")


__all__ = [
    "InboundOperationEntryIn",
    "InboundOperationLineIn",
    "InboundOperationSubmitIn",
    "InboundOperationLineOut",
    "InboundOperationSubmitOut",
]
