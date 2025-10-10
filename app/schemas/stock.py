# app/schemas/stock.py
from datetime import date

from pydantic import BaseModel, Field

try:
    # Pydantic v2
    from pydantic import ConfigDict, field_validator

    _IS_V2 = True
except Exception:
    from pydantic import validator

    _IS_V2 = False


class _StrictBase(BaseModel):
    if _IS_V2:
        model_config = ConfigDict(from_attributes=True, extra="forbid")
    else:

        class Config:
            orm_mode = True
            extra = "forbid"


# ----------------------------
# 现有：库存增减入参/出参
# + 扩展：批次与 FEFO 支持
# ----------------------------
class StockAdjustIn(_StrictBase):
    item_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    delta: int = Field(..., description="正数入库，负数出库")
    reason: str | None = Field(None, max_length=200)
    ref: str | None = Field(None, max_length=100, description="幂等参考号")
    allow_negative: bool = False

    # 新增：定向批次入库/出库用；FEFO 时可忽略
    batch_code: str | None = Field(None, max_length=100)
    production_date: date | None = None
    expiry_date: date | None = None

    # 新增：出库模式（NORMAL | FEFO）
    mode: str = Field("NORMAL", description="NORMAL|FEFO")
    allow_expired: bool = False  # ← 新增：FEFO 出库是否允许使用已过期批次（默认不允许

    if _IS_V2:

        @field_validator("delta")
        def _delta_non_zero(cls, v: int) -> int:
            if v == 0:
                raise ValueError("delta 不能为 0")
            return v

    else:

        @validator("delta")
        def _delta_non_zero_v1(cls, v: int):
            if v == 0:
                raise ValueError("delta 不能为 0")
            return v


class StockAdjustOut(_StrictBase):
    item_id: int
    location_id: int
    before_quantity: int
    delta: int
    new_quantity: int
    applied: bool = True
    message: str = "OK"


class StockRow(_StrictBase):
    item_id: int
    location_id: int
    quantity: int
    warehouse_id: int | None = None


class StockSummary(_StrictBase):
    item_id: int
    on_hand: int


class StockQueryOut(_StrictBase):
    rows: list[StockRow]
    summary: list[StockSummary]


# ----------------------------
# 新增：批次查询入参/出参（v4）
# ----------------------------
class StockBatchQueryIn(_StrictBase):
    """POST /stock/batch/query 入参"""

    item_id: int | None = Field(None, ge=1)
    warehouse_id: int | None = Field(None, ge=1)
    expiry_date_from: date | None = None
    expiry_date_to: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class StockBatchRow(_StrictBase):
    batch_id: int
    item_id: int
    warehouse_id: int
    batch_code: str
    qty: int
    production_date: date | None = None
    expiry_date: date | None = None
    # 负数表示已过期
    days_to_expiry: int | None = Field(None, description="到期天数(负数=已过期)")


class StockBatchQueryOut(_StrictBase):
    total: int
    page: int
    page_size: int
    items: list[StockBatchRow]


class TransferExpiredIn(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    # 二选一：指定目标库位 ID，或用 name 自动创建/复用（默认 EXPIRED_ZONE）
    to_location_id: int | None = Field(None, ge=1)
    to_location_name: str = Field("EXPIRED_ZONE", max_length=100)
    # 可选过滤：仅处理这些 item_id；不传则处理仓内所有已过期批次
    item_ids: list[int] | None = None
    # 干跑：只返回计划，不落库
    dry_run: bool = False


class TransferExpiredMove(BaseModel):
    item_id: int
    batch_id_src: int
    batch_code: str
    src_location_id: int
    dst_location_id: int
    qty_moved: int


class TransferExpiredOut(BaseModel):
    warehouse_id: int
    moved_total: int
    moves: list[TransferExpiredMove]


# === 盘点 / 差异调整 ===


class InventoryReconcileIn(BaseModel):
    item_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=1)
    counted_qty: float = Field(..., description="盘点实数")
    apply: bool = Field(True, description="是否落库（False=干跑）")
    ref: str | None = Field(None, max_length=128)


class InventoryMove(BaseModel):
    batch_id: int | str
    used_delta: float


class InventoryReconcileOut(BaseModel):
    item_id: int
    location_id: int
    before_qty: float
    counted_qty: float
    diff: float
    applied: bool
    after_qty: float | None = None
    moves: list[tuple[int | str, float]] = []


# === 调拨（Transfer） ===


class StockTransferIn(BaseModel):
    item_id: int = Field(..., ge=1)
    src_location_id: int = Field(..., ge=1)
    dst_location_id: int = Field(..., ge=1)
    qty: float = Field(..., gt=0)
    allow_expired: bool = False
    reason: str = "TRANSFER"
    ref: str | None = None


class StockTransferMove(BaseModel):
    src_batch_id: int
    dst_batch_id: int
    batch_code: str
    qty: int


class StockTransferOut(BaseModel):
    item_id: int
    src_location_id: int
    dst_location_id: int
    total_moved: int
    moves: list[StockTransferMove]
