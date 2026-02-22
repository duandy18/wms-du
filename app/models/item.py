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
    Item 主数据模型 —— 对齐 public.items

    关键区分：
    - has_shelf_life（开关）：是否需要有效期管理（= 入库是否强制日期）
      * True  -> 入库必须填写生产日期；到期日期可直接填，或由保质期参数推算
      * False -> 入库不需要日期；库存核算层走“无批次槽位”（batch_code=NULL）
    - shelf_life_value/unit（参数）：可选保质期参数，用于 production_date + 参数 => 推算 expiry_date
      * 注意：参数不是必须；若缺参数，则入库必须直接填 expiry_date

    库存说明（重要）：
    - items 表不承载可用库存的真实事实。
    - 库存真实来源：stocks / stock_ledger / stock_snapshots（以及三账一致性校验）。
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

    # ✅ 事实单位（唯一口径）：DB 列名已迁移为 items.uom
    uom: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        server_default=text("'PCS'::character varying"),
    )

    # ✅ Phase 1: 结构化包装字段（一层箱装）
    # 语义：1 case_uom = case_ratio × uom（最小单位）
    # 注意：case_uom 是展示/输入偏好标签，不改变系统事实口径；可为空（未治理）
    case_ratio: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="箱装换算倍率（整数）；1 case_uom = case_ratio × uom（最小单位）；允许为空（未治理）",
    )
    case_uom: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="箱装单位名（展示/输入偏好），如“箱”；允许为空（未治理）",
    )

    spec: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    # ✅ 新增：品牌/品类（主数据字段，允许为空，逐步治理）
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ✅ 新增：有效期管理开关（事实字段）
    has_shelf_life: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="是否需要有效期管理（入库是否强制日期）",
    )

    weight_kg: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="单件净重（kg），用于运费预估，不含包材",
    )

    # ✅ 可选保质期参数（用于推算到期日）
    shelf_life_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shelf_life_unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", name="fk_items_supplier", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", lazy="joined")

    @property
    def unit(self) -> str:
        # ✅ 兼容旧调用：Item.unit -> Item.uom（只读）
        return self.uom

    @property
    def barcode(self) -> Optional[str]:
        # ✅ 兼容输出：旧字段 barcode = 主条码（primary_barcode）
        return getattr(self, "primary_barcode", None)

    @property
    def supplier_name(self) -> Optional[str]:
        return self.supplier.name if self.supplier is not None else None

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
        return (
            f"<Item id={self.id} sku={self.sku!r} name={self.name!r} "
            f"brand={self.brand!r} category={self.category!r} "
            f"has_shelf_life={self.has_shelf_life} "
            f"case_ratio={self.case_ratio!r} case_uom={self.case_uom!r}>"
        )
