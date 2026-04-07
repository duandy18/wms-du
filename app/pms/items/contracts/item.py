# app/pms/items/contracts/item.py
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


def _is_required_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


class NextSkuOut(_Base):
    sku: str


class ItemBase(_Base):
    sku: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    # 兼容字段：历史上前端/调用方使用 barcode 表示“主条码”
    # 本轮收敛：primary_barcode 才是唯一真相；barcode 作为 alias（输出时等同 primary_barcode）
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None
    primary_barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: Annotated[int | None, Field(default=None)] = None

    # -------------------------
    # Phase M Rule layer
    # -------------------------
    lot_source_policy: Annotated[Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"] | None, Field(default=None)] = None
    expiry_policy: Annotated[Literal["NONE", "REQUIRED"] | None, Field(default=None)] = None
    derivation_allowed: Annotated[bool | None, Field(default=None)] = None
    uom_governance_enabled: Annotated[bool | None, Field(default=None)] = None

    # 旧字段（兼容输入/输出，但真相以 expiry_policy 为准）
    has_shelf_life: Annotated[bool | None, Field(default=None)] = None

    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
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

    Phase M-3：
    - items.case_ratio/case_uom 已删除；包装单位请走 item_uoms
    """

    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    # 兼容：创建时允许传入 barcode，后端会写入 item_barcodes 并设为主条码
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: int | None = None

    # Phase M：允许显式传 policy（不给也行，后端可有默认）
    lot_source_policy: Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"] | None = None
    expiry_policy: Literal["NONE", "REQUIRED"] | None = None
    derivation_allowed: bool | None = None
    uom_governance_enabled: bool | None = None

    # 旧字段（保留兼容，但最终以 expiry_policy 为准）
    has_shelf_life: bool | None = None
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "name",
        "spec",
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

    # 保留字段（兼容），但 router 会拒绝通过 /items 更新 barcode，要求走 /item-barcodes
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = None
    supplier_id: int | None = None

    # Phase M policy：允许更新（测试环境一步到位）
    lot_source_policy: Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"] | None = None
    expiry_policy: Literal["NONE", "REQUIRED"] | None = None
    derivation_allowed: bool | None = None
    uom_governance_enabled: bool | None = None

    # 旧字段（兼容；但 DB 已锁死与 expiry_policy 一致）
    has_shelf_life: bool | None = None
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[Literal["DAY", "MONTH"] | None, Field(default=None)] = None

    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
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
                "barcode",
                "brand",
                "category",
                "enabled",
                "supplier_id",
                "lot_source_policy",
                "expiry_policy",
                "derivation_allowed",
                "uom_governance_enabled",
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

    Phase M-3：
    - items.case_ratio/case_uom 已删除；包装单位请走 item_uoms
    """

    id: Annotated[int, Field(gt=0)]

    sku: Annotated[str | None, Field(default=None, max_length=128)] = None
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    # ✅ 新增：品牌/品类
    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = True
    supplier_id: int | None = None

    # Phase M policy
    lot_source_policy: Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"] | None = None
    expiry_policy: Literal["NONE", "REQUIRED"] | None = None
    derivation_allowed: bool | None = None
    uom_governance_enabled: bool | None = None

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

    @model_validator(mode="after")
    def _derive_require_flags(self):
        # Phase M：由 expiry_policy 投影
        req = _is_required_expiry_policy(self.expiry_policy)
        self.requires_batch = bool(req)
        self.requires_dates = bool(req)
        return self


__all__ = [
    "NextSkuOut",
    "ItemBase",
    "ItemCreate",
    "ItemUpdate",
    "ItemCreateById",
    "ItemOut",
]
