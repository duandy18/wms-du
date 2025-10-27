from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 统一使用项目全局 Base
from app.db.base import Base


# === stores ================================================================

class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="pdd")

    # 现有占位（如有加密/外管，可后续替换）
    api_token: Mapped[bytes | None] = mapped_column(nullable=True)

    # ★ 新增预留：平台凭据/回调（全可空，便于后续接 SDK）
    app_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    app_secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    callback_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[List["StoreItem"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )
    inventories: Mapped[List["ChannelInventory"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )


# === store_items ===========================================================

class StoreItem(Base):
    __tablename__ = "store_items"
    __table_args__ = (
        UniqueConstraint("store_id", "pdd_sku_id", name="uq_store_items_store_pddsku"),
        UniqueConstraint("store_id", "item_id", name="uq_store_items_store_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    pdd_sku_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    store: Mapped["Store"] = relationship(back_populates="items")


# === channel_inventory =====================================================

class ChannelInventory(Base):
    __tablename__ = "channel_inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "item_id", name="uq_channel_inventory_store_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )

    # A 策略参数：配额上限（NULL 表示无限）
    cap_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 该店对该内品的占用合计
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 对平台可见量（可由服务计算刷新）
    visible_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    store: Mapped["Store"] = relationship(back_populates="inventories")
