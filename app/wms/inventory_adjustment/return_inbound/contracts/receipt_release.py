from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReceiptReleaseOut(_Base):
    receipt_id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    status: Literal["RELEASED"] = Field(description="发布后状态")
    released_at: datetime = Field(description="发布时间")


__all__ = [
    "InboundReceiptReleaseOut",
]
