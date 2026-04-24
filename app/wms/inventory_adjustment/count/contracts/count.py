from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CountRequest(BaseModel):
    """
    盘点校正请求（批次级）：

    - 必填：item_id, warehouse_id, qty(绝对量), ref
    - lot_code 为唯一批次展示码入参；batch_code alias 已退役
    - production_date / expiry_date：仅对批次受控商品要求至少其一
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    item_id: int = Field(..., description="商品ID")
    warehouse_id: int = Field(..., ge=1, description="仓库ID")
    qty: int = Field(..., ge=0, description="盘点后的实际数量（绝对量）")
    ref: str = Field(..., description="业务参考号（用于台账幂等）")

    lot_code: Optional[str] = Field(None, description="Lot 展示码")

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="盘点发生时间（UTC）；默认当前时间",
    )
    production_date: Optional[datetime] = Field(None, description="生产日期（可选）")
    expiry_date: Optional[datetime] = Field(None, description="有效期（可选）")

    @model_validator(mode="after")
    def _normalize_time(self) -> "CountRequest":
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class CountResponse(BaseModel):
    ok: bool = True
    after: int
    ref: str
    item_id: int
    warehouse_id: int

    lot_code: Optional[str] = None
    occurred_at: datetime
