from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class InventoryQuery(_Base):
    q: Optional[str] = Field(default=None, description="按商品编码/名称模糊搜索")
    item_id: Optional[int] = Field(default=None, ge=1, description="商品 ID（精确）")
    warehouse_id: Optional[int] = Field(default=None, ge=1, description="仓库 ID（精确）")
    lot_code: Optional[str] = Field(default=None, max_length=64, description="Lot 展示码（精确）")
    near_expiry: Optional[bool] = Field(default=None, description="是否只看临期")
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20

    @field_validator("q", "lot_code", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class InventoryRow(_Base):
    item_id: Annotated[int, Field(ge=1)]
    item_name: Annotated[str, Field(min_length=0, max_length=128)]

    item_code: Optional[str] = None
    spec: Optional[str] = None
    main_barcode: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None

    warehouse_id: Annotated[int, Field(ge=1)]
    lot_code: Optional[str] = None

    qty: int
    expiry_date: date | None = None
    near_expiry: bool = False
    days_to_expiry: Optional[int] = None


class InventoryResponse(_Base):
    total: Annotated[int, Field(ge=0)]
    offset: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=100)]
    rows: list[InventoryRow] = Field(default_factory=list)


class InventoryDetailQuery(_Base):
    warehouse_id: Optional[int] = Field(default=None, ge=1)
    lot_code: Optional[str] = Field(default=None, max_length=64)
    pools: list[str] = Field(default_factory=lambda: ["MAIN"])

    @field_validator("lot_code", mode="before")
    @classmethod
    def _trim_lot_code(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class InventoryDetailTotals(_Base):
    on_hand_qty: Annotated[int, Field(ge=0)]
    available_qty: Annotated[int, Field(ge=0)]


class InventoryDetailSlice(_Base):
    warehouse_id: Annotated[int, Field(ge=1)]
    warehouse_name: Annotated[str, Field(min_length=1, max_length=100)]
    pool: Annotated[str, Field(min_length=1, max_length=32)]

    lot_code: Optional[str] = None
    production_date: date | None = None
    expiry_date: date | None = None

    on_hand_qty: Annotated[int, Field(ge=0)]
    available_qty: Annotated[int, Field(ge=0)]

    near_expiry: bool = False
    is_top: bool = False


class InventoryDetailResponse(_Base):
    item_id: Annotated[int, Field(ge=1)]
    item_name: Annotated[str, Field(min_length=0, max_length=128)]

    totals: InventoryDetailTotals
    slices: list[InventoryDetailSlice] = Field(default_factory=list)


__all__ = [
    "InventoryQuery",
    "InventoryRow",
    "InventoryResponse",
    "InventoryDetailQuery",
    "InventoryDetailTotals",
    "InventoryDetailSlice",
    "InventoryDetailResponse",
]
