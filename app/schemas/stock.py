# app/schemas/stock.py
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ✅ 引用统一业务枚举
from app.models.enum import MovementType


# ========= 通用基类 =========
class _Base(BaseModel):
    """允许 ORM 输出、忽略多余字段，确保兼容旧客户端"""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


# ========= 库存调整（Adjust） =========
class StockAdjustIn(_Base):
    """库存调整入参（正数=入库, 负数=出库）"""

    item_id: Annotated[int, Field(ge=1)]
    location_id: Annotated[int, Field(ge=1)]
    delta: Annotated[int, Field(description="库存变动量；正数入库，负数出库")]
    reason: Annotated[str | None, Field(None, max_length=200)] = None
    ref: Annotated[str | None, Field(None, max_length=128)] = None
    allow_negative: bool = False
    batch_code: Annotated[str | None, Field(None, max_length=100)] = None
    production_date: date | None = None
    expiry_date: date | None = None
    mode: Literal["NORMAL", "FEFO"] = "NORMAL"
    allow_expired: bool = False
    movement_type: MovementType = MovementType.ADJUSTMENT

    @field_validator("delta")
    @classmethod
    def _nonzero(cls, v: int):
        if v == 0:
            raise ValueError("delta 不能为 0")
        return v


class StockAdjustOut(_Base):
    """库存调整结果"""

    item_id: int
    location_id: int
    before_quantity: int
    delta: int
    new_quantity: int
    movement_type: MovementType = MovementType.ADJUSTMENT
    applied: bool = True
    message: str = "OK"


# ========= 库存查询（Query） =========
class StockRow(_Base):
    """库存明细行"""

    item_id: int
    location_id: int
    quantity: int
    warehouse_id: int | None = None


class StockSummary(_Base):
    """库存汇总行"""

    item_id: int
    on_hand: int


class StockQueryOut(_Base):
    """库存查询响应"""

    rows: list[StockRow] = Field(default_factory=list)
    summary: list[StockSummary] = Field(default_factory=list)


# ========= 批次查询（Batch） =========
class StockBatchQueryIn(_Base):
    """POST /stock/batch/query 入参"""

    item_id: int | None = Field(None, ge=1)
    warehouse_id: int | None = Field(None, ge=1)
    expiry_date_from: date | None = None
    expiry_date_to: date | None = None
    page: Annotated[int, Field(default=1, ge=1)]
    page_size: Annotated[int, Field(default=50, ge=1, le=500)]


class StockBatchRow(_Base):
    """批次行"""

    batch_id: int
    item_id: int
    warehouse_id: int
    batch_code: str
    qty: int
    production_date: date | None = None
    expiry_date: date | None = None
    days_to_expiry: Annotated[int | None, Field(None, description="到期天数(负数=已过期)")] = None


class StockBatchQueryOut(_Base):
    """批次查询结果"""

    total: int
    page: int
    page_size: int
    items: list[StockBatchRow] = Field(default_factory=list)


# ========= 过期转移（Transfer Expired） =========
class TransferExpiredIn(_Base):
    """
    将仓内所有（或指定 item_id 集）已过期批次转移至指定库位/默认过期区。
    - dry_run=True 时仅返回计划，不落库。
    """

    warehouse_id: Annotated[int, Field(ge=1)]
    to_location_id: Annotated[int | None, Field(None, ge=1)] = None
    to_location_name: Annotated[str, Field(default="EXPIRED_ZONE", max_length=100)] = "EXPIRED_ZONE"
    item_ids: list[int] | None = None
    dry_run: bool = False


class TransferExpiredMove(_Base):
    item_id: int
    batch_id_src: int
    batch_code: str
    src_location_id: int
    dst_location_id: int
    qty_moved: int


class TransferExpiredOut(_Base):
    warehouse_id: int
    moved_total: int
    moves: list[TransferExpiredMove] = Field(default_factory=list)


# ========= 盘点 / 差异调整（Reconcile） =========
class InventoryReconcileIn(_Base):
    """盘点：以实盘数量为准；apply=False 时仅仿真"""

    item_id: Annotated[int, Field(ge=1)]
    location_id: Annotated[int, Field(ge=1)]
    counted_qty: Annotated[float, Field(ge=0)]
    apply: bool = True
    ref: Annotated[str | None, Field(None, max_length=128)] = None


class InventoryMove(_Base):
    batch_id: int | str
    used_delta: float


class InventoryReconcileOut(_Base):
    item_id: int
    location_id: int
    before_qty: float
    counted_qty: float
    diff: float
    applied: bool
    after_qty: float | None = None
    moves: list[tuple[int | str, float]] = Field(default_factory=list)


# ========= 调拨（Transfer） =========
class StockTransferIn(_Base):
    """同仓调拨（src_location → dst_location）"""

    item_id: Annotated[int, Field(ge=1)]
    src_location_id: Annotated[int, Field(ge=1)]
    dst_location_id: Annotated[int, Field(ge=1)]
    qty: Annotated[float, Field(gt=0)]
    allow_expired: bool = False
    reason: str = "TRANSFER"
    ref: str | None = None


class StockTransferMove(_Base):
    src_batch_id: int
    dst_batch_id: int
    batch_code: str
    qty: int


class StockTransferOut(_Base):
    item_id: int
    src_location_id: int
    dst_location_id: int
    total_moved: int
    moves: list[StockTransferMove] = Field(default_factory=list)
