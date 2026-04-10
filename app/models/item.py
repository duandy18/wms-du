# app/models/item.py
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .item_uom import ItemUOM
    from .order import Order
    from .order_item import OrderItem
    from .supplier import Supplier


class LotSourcePolicy(str, enum.Enum):
    INTERNAL_ONLY = "INTERNAL_ONLY"
    SUPPLIER_ONLY = "SUPPLIER_ONLY"


class ExpiryPolicy(str, enum.Enum):
    NONE = "NONE"
    REQUIRED = "REQUIRED"


class Item(Base):
    """
    Item 主数据模型 —— 对齐 public.items

    Phase M 关键变化（规则上移，禁止隐式推断）：
    - expiry_policy 是有效期规则真相源（NONE / REQUIRED）
    - lot_source_policy / derivation_allowed / uom_governance_enabled 为执行层只读策略开关

    Phase M-3（结构减法）：
    - items.case_ratio / items.case_uom 已物理删除；包装倍率真相源 = item_uoms

    Phase M-5（unit_governance 二阶段）：
    - items.uom 已物理移除
    - base_uom 的事实口径 = item_uoms.is_base=true（结构层）

    Phase M-6（item weight cutover）：
    - items.weight_kg 已物理删除
    - 运行时 weight_kg = base item_uom.net_weight_kg
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    spec: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    lot_source_policy: Mapped[LotSourcePolicy] = mapped_column(
        Enum(LotSourcePolicy, name="lot_source_policy", native_enum=True),
        nullable=False,
    )
    expiry_policy: Mapped[ExpiryPolicy] = mapped_column(
        Enum(ExpiryPolicy, name="expiry_policy", native_enum=True),
        nullable=False,
    )
    derivation_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    uom_governance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    shelf_life_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shelf_life_unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", name="fk_items_supplier", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", lazy="joined")

    uoms: Mapped[List["ItemUOM"]] = relationship(
        "ItemUOM",
        back_populates="item",
        lazy="selectin",
        order_by="ItemUOM.id.asc()",
    )

    @property
    def unit(self) -> str:
        """
        Phase M-5：对外兼容字段
        - items.uom 已移除；只能从结构层 base item_uom 读取
        """
        base = self.get_base_uom()
        if base is None or not getattr(base, "uom", None):
            raise RuntimeError(f"item missing base item_uom (is_base=true): item_id={int(self.id)}")
        return str(getattr(base, "uom"))

    @property
    def weight_kg(self) -> Optional[float]:
        """
        Phase M-6：只读输出投影
        - items.weight_kg 已物理删除
        - 运行时真相源 = base item_uom.net_weight_kg
        """
        base = self.get_base_uom()
        if base is None:
            return None
        raw = getattr(base, "net_weight_kg", None)
        if raw is None:
            return None
        return float(raw)

    @property
    def barcode(self) -> Optional[str]:
        return getattr(self, "primary_barcode", None)

    @property
    def supplier_name(self) -> Optional[str]:
        return self.supplier.name if self.supplier is not None else None

    def get_base_uom(self) -> Optional["ItemUOM"]:
        for u in self.uoms or []:
            if getattr(u, "is_base", False):
                return u
        return None

    def get_default_purchase_uom(self) -> Optional["ItemUOM"]:
        for u in self.uoms or []:
            if getattr(u, "is_purchase_default", False):
                return u
        return self.get_base_uom()

    def get_default_inbound_uom(self) -> Optional["ItemUOM"]:
        for u in self.uoms or []:
            if getattr(u, "is_inbound_default", False):
                return u
        return self.get_base_uom()

    def get_default_outbound_uom(self) -> Optional["ItemUOM"]:
        for u in self.uoms or []:
            if getattr(u, "is_outbound_default", False):
                return u
        return self.get_base_uom()

    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="item",
        lazy="selectin",
    )

    orders: Mapped[List["Order"]] = relationship(
        "Order",
        secondary="order_items",
        viewonly=True,
        lazy="selectin",
        back_populates="items",
    )

    def __repr__(self) -> str:
        return (
            f"<Item id={self.id} sku={self.sku!r} name={self.name!r} "
            f"brand={self.brand!r} category={self.category!r} "
            f"expiry_policy={self.expiry_policy}>"
        )
