# app/models/item.py
# app/models/item.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .order import Order
    from .order_item import OrderItem
    from .stock import Stock
    from .supplier import Supplier


class Item(Base):
    """
    Item 主数据模型 —— 对齐 public.items:

        id                  INTEGER PRIMARY KEY
        sku                 VARCHAR(64) UNIQUE NOT NULL
        name                VARCHAR(128) NOT NULL
        qty_available       INTEGER NOT NULL DEFAULT 0
        created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        unit                VARCHAR(8) NOT NULL DEFAULT 'PCS'
        shelf_life_days     INTEGER NULL               （旧字段，按天）
        shelf_life_value    INTEGER NULL               （新字段：保质期数值）
        shelf_life_unit     VARCHAR(16) NULL           （新字段：DAY / MONTH）
        spec                VARCHAR(128) NULL
        enabled             BOOLEAN NOT NULL DEFAULT true
        supplier_id         INTEGER NULL REFERENCES suppliers(id)
        weight_kg           NUMERIC(10,3) NULL         （单件净重，kg）
    """

    __tablename__ = "items"

    # ---------- 主键 ----------
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ---------- 基础字段 ----------
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    qty_available: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

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

    unit: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        server_default=text("'PCS'::character varying"),
    )

    spec: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    # ---------- 新增：单件净重（kg），用于运费预估 ----------
    weight_kg: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="单件净重（kg），用于运费预估，不含包材",
    )

    # ============================================================
    # 保质期字段：旧字段（days）+ 新字段（value + unit）
    # ============================================================

    # 旧：仍然保留历史兼容
    shelf_life_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # 新：通用保质期（数值 + 单位）
    shelf_life_value: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    shelf_life_unit: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
    )

    # ---------- 供应商 ----------
    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier: Mapped[Optional["Supplier"]] = relationship(
        "Supplier",
        lazy="joined",
    )

    # ---------- 只读属性给 Pydantic 用 ----------
    @property
    def uom(self) -> str:
        """把 unit 暴露为 uom，ItemOut.uom 直接用这个。"""
        return self.unit

    @property
    def barcode(self) -> Optional[str]:
        """
        占位属性：当前阶段条码未接 item_barcodes，
        先返回 None，避免 Pydantic 报错。
        未来条码管理 Phase 会改成查 item_barcodes。
        """
        return None

    @property
    def supplier_name(self) -> Optional[str]:
        """默认供应商名称"""
        return self.supplier.name if self.supplier is not None else None

    # ---------- 关联关系 ----------
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

    stocks: Mapped[List["Stock"]] = relationship(
        "Stock",
        back_populates="item",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} sku={self.sku!r} name={self.name!r}>"
