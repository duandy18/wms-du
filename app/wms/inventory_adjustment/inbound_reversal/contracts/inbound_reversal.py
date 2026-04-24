from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.wms.inbound.contracts.inbound_commit import InboundSourceType


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReversalIn(_Base):
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="冲回业务发生时间",
    )
    operator_name_snapshot: Annotated[
        str,
        Field(min_length=1, max_length=64, description="操作人员姓名"),
    ]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="冲回备注")]

    @model_validator(mode="after")
    def _normalize_time(self) -> "InboundReversalIn":
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class InboundReversalRowOut(_Base):
    line_no: Annotated[int, Field(ge=1, description="事件行号")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    lot_id: Annotated[int, Field(ge=1, description="lot_id")]
    qty_base: Annotated[int, Field(ge=1, description="冲回 base 数量")]


class InboundReversalOut(_Base):
    ok: bool = Field(default=True, description="是否成功")
    event_id: Annotated[int, Field(ge=1, description="冲回事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="冲回事件单号")]
    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="技术链路追踪号")]
    target_event_id: Annotated[int, Field(ge=1, description="被冲回的原事件 ID")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: InboundSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(description="冲回业务发生时间")
    operator_name_snapshot: Annotated[str, Field(min_length=1, max_length=64, description="操作人员姓名")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="冲回备注")]
    rows: list[InboundReversalRowOut] = Field(default_factory=list, description="冲回结果行")


__all__ = [
    "InboundReversalIn",
    "InboundReversalRowOut",
    "InboundReversalOut",
]
