# app/schemas/item.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


def _norm_text(v):
    return v.strip() if isinstance(v, str) else v


class NextSkuOut(_Base):
    sku: str


class ItemBase(_Base):
    sku: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None

    # ✅ Phase 1: 结构化包装字段（仅一层箱装）
    # 语义：1 case_uom = case_ratio × uom（最小单位）
    # 注意：uom 是系统事实口径；case_* 不改变事实口径，仅用于展示/输入偏好与换算
    case_ratio: Annotated[int | None, Field(default=None, ge=1)] = None
    case_uom: Annotated[str | None, Field(default=None, max_length=16)] = None

    # 兼容字段：历史上前端/调用方使用 barcode 表示“主条码”
    # 本轮收敛：primary_barcode 才是唯一真相；barcode 作为 alias（输出时等同 primary_barcode）
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None
    primary_barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: Annotated[int | None, Field(default=None)] = None

    has_shelf_life: Annotated[bool | None, Field(default=None)] = None

    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
        "uom",
        "case_uom",
        "barcode",
        "primary_barcode",
        "brand",
        "category",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v):
        return _norm_text(v)


class ItemCreate(_Base):
    """
    Create Item（统一由后端生成 SKU）：
    - 不接受 sku 输入
    """

    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None

    # ✅ Phase 1: 结构化包装字段（仅一层箱装）
    case_ratio: Annotated[int | None, Field(default=None, ge=1)] = None
    case_uom: Annotated[str | None, Field(default=None, max_length=16)] = None

    # 兼容：创建时允许传入 barcode，后端会写入 item_barcodes 并设为主条码
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: int | None = None

    has_shelf_life: bool | None = None
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "name",
        "spec",
        "uom",
        "case_uom",
        "barcode",
        "brand",
        "category",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v):
        return _norm_text(v)


class ItemUpdate(_Base):
    # 允许更新 sku 吗？——本轮先不开放（router 已强制拒绝 sku）
    sku: Annotated[str | None, Field(default=None, max_length=128)] = None

    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None

    # ✅ Phase 1: 结构化包装字段（仅一层箱装）
    case_ratio: Annotated[int | None, Field(default=None, ge=1)] = None
    case_uom: Annotated[str | None, Field(default=None, max_length=16)] = None

    # 保留字段（兼容），但 router 会拒绝通过 /items 更新 barcode，要求走 /item-barcodes
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = None
    supplier_id: int | None = None

    has_shelf_life: bool | None = None
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
        "uom",
        "case_uom",
        "barcode",
        "brand",
        "category",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v):
        return _norm_text(v)

    @model_validator(mode="after")
    def _at_least_one(self):
        if all(
            getattr(self, f) is None
            for f in (
                "sku",
                "name",
                "spec",
                "uom",
                "case_ratio",
                "case_uom",
                "barcode",
                "brand",
                "category",
                "enabled",
                "supplier_id",
                "has_shelf_life",
                "shelf_life_value",
                "shelf_life_unit",
                "weight_kg",
            )
        ):
            raise ValueError("至少提供一个更新字段")
        return self


class ItemCreateById(_Base):
    """
    这个接口本身就是“例外通道”，用于历史兼容/修复。
    如果你也想“完全统一标准”，建议在 router 层直接禁用该接口（删除 /by-id 路由）。
    """

    id: Annotated[int, Field(gt=0)]

    sku: Annotated[str | None, Field(default=None, max_length=128)] = None
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None

    # ✅ Phase 1: 结构化包装字段（仅一层箱装）
    case_ratio: Annotated[int | None, Field(default=None, ge=1)] = None
    case_uom: Annotated[str | None, Field(default=None, max_length=16)] = None

    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = True
    supplier_id: int | None = None

    has_shelf_life: bool | None = None
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None


class ItemOut(ItemBase):
    id: int
    supplier_name: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    requires_batch: bool = True
    requires_dates: bool = True
    default_batch_code: Optional[str] = None

    # ✅ 新增：是否为 DEFAULT Test Set 商品（由后端投影，前端可显性化）
    is_test: bool = False


__all__ = [
    "NextSkuOut",
    "ItemBase",
    "ItemCreate",
    "ItemUpdate",
    "ItemCreateById",
    "ItemOut",
]
