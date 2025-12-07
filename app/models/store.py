from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.warehouse import Warehouse


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        # 平台 + shop_id 全局唯一
        UniqueConstraint("platform", "shop_id", name="uq_stores_platform_shop"),
        # 常用查询：按平台+状态筛店
        Index("ix_stores_platform_active", "platform", "active"),
        # 按 shop_id 查店铺（与 drift 中 ix_stores_shop 对齐）
        Index("ix_stores_shop", "shop_id"),
        # 手动维护索引/约束，不走 autogenerate
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    # 已在迁移中强制 NOT NULL + 128 长度
    shop_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # 已在迁移中扩到 256
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="NO-STORE")

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ==== 新增：店铺主数据扩展字段 ====
    # 邮箱（客服 / 对账 / 通知）
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # 联系人姓名
    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 联系电话（手机 / 座机 / 分机）
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 多仓关系（通过中间表 store_warehouse）
    warehouses: Mapped[List["Warehouse"]] = relationship(
        "Warehouse",
        secondary="store_warehouse",
        backref=backref(
            "stores",
            lazy="selectin",
            overlaps="store_warehouses,store,warehouse",
        ),
        lazy="selectin",
        passive_deletes=True,
        overlaps="store_warehouses,store,warehouse",
    )

    store_warehouses: Mapped[List["StoreWarehouse"]] = relationship(
        "StoreWarehouse",
        back_populates="store",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        overlaps="warehouses,stores,warehouse",
    )

    items: Mapped[List["StoreItem"]] = relationship(
        "StoreItem",
        back_populates="store",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    inventories: Mapped[List["ChannelInventory"]] = relationship(
        "ChannelInventory",
        back_populates="store",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Store id={self.id} platform={self.platform} "
            f"shop_id={self.shop_id!r} active={self.active}>"
        )


class StoreWarehouse(Base):
    __tablename__ = "store_warehouse"
    __table_args__ = (
        # 一个店铺在同一仓只能映射一次
        UniqueConstraint("store_id", "warehouse_id", name="uq_store_wh_unique"),
        # 用于选择“默认仓/优先级”
        Index("ix_store_wh_store_default", "store_id", "is_default", "priority"),
        {"info": {"skip_autogen": True}},
    )

    # DB 当前 id 仍为 BIGINT（我们没有在迁移里改 id），这里保持 BigInteger
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # store_id / warehouse_id 在迁移中已从 BIGINT 收缩为 INTEGER，这里显式对齐 Integer
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Phase 3.9 新增，用于标记“主仓”
    is_top: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 旧逻辑保留：is_default + priority 用于路由策略
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    store: Mapped["Store"] = relationship(
        "Store",
        back_populates="store_warehouses",
        overlaps="warehouses,stores,warehouse",
    )
    warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse",
        overlaps="stores,warehouses,store",
    )

    def __repr__(self) -> str:
        return (
            f"<StoreWarehouse id={self.id} store_id={self.store_id} "
            f"warehouse_id={self.warehouse_id} "
            f"default={self.is_default} top={self.is_top} prio={self.priority}>"
        )


class StoreItem(Base):
    __tablename__ = "store_items"
    __table_args__ = (
        UniqueConstraint("store_id", "pdd_sku_id", name="uq_store_items_store_pddsku"),
        UniqueConstraint("store_id", "item_id", name="uq_store_items_store_item"),
        Index("ix_store_items_store_item", "store_id", "item_id"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    pdd_sku_id: Mapped[Optional[str]] = mapped_column(String(64))
    outer_id: Mapped[Optional[str]] = mapped_column(String(128))

    store: Mapped["Store"] = relationship("Store", back_populates="items")

    def __repr__(self) -> str:
        return f"<StoreItem id={self.id} store_id={self.store_id} item_id={self.item_id}>"


class ChannelInventory(Base):
    __tablename__ = "channel_inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "item_id", name="uq_channel_inventory_store_item"),
        Index("ix_channel_inventory_store_item", "store_id", "item_id"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # cap_qty: NULL 表示“无限”
    cap_qty: Mapped[Optional[int]] = mapped_column(Integer)
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visible_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    store: Mapped["Store"] = relationship("Store", back_populates="inventories")

    def __repr__(self) -> str:
        return (
            f"<ChannelInventory id={self.id} store_id={self.store_id} "
            f"item_id={self.item_id} visible={self.visible_qty}>"
        )
