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
        UniqueConstraint("platform", "shop_id", name="uq_stores_platform_shop"),
        UniqueConstraint("platform", "store_code", name="uq_stores_platform_store_code"),
        Index("ix_stores_platform_active", "platform", "active"),
        Index("ix_stores_shop", "shop_id"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="NO-STORE")

    # ✅ 对外稳定短码：用于 PSKU code 生成（平台后台填写）
    store_code: Mapped[str] = mapped_column(String(32), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
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
        UniqueConstraint("store_id", "warehouse_id", name="uq_store_wh_unique"),
        Index("ix_store_wh_store_default", "store_id", "is_default", "priority"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

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

    is_top: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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

    cap_qty: Mapped[Optional[int]] = mapped_column(Integer)
    visible_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    store: Mapped["Store"] = relationship("Store", back_populates="inventories")

    def __repr__(self) -> str:
        return (
            f"<ChannelInventory id={self.id} store_id={self.store_id} "
            f"item_id={self.item_id} visible={self.visible_qty}>"
        )
