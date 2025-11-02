# app/models/store.py
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
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 统一使用项目全局 Base
from app.db.base import Base


# ========================================================================
# stores —— 店铺主档
# ========================================================================

class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        # 同一平台下店铺名唯一（可按需调整为 seller_id 等）
        UniqueConstraint("platform", "name", name="uq_stores_platform_name"),
        # 常用检索索引
        Index("ix_stores_platform_active", "platform", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 平台标识（如 pdd / tb / jd），保持小写短码；默认 pdd
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="pdd")
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 可选：平台接入所需凭据（先明文存储，后续可接 KMS/加密）
    app_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    app_secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    callback_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # 占位的 token（后续若改为密文/外管，这里换类型与列名即可）
    api_token: Mapped[bytes | None] = mapped_column(nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 具时区时间；DB 层统一存 UTC，展示层再转 Asia/Shanghai
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

    # 关系：店铺下的映射与渠道库存
    items: Mapped[List["StoreItem"]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    inventories: Mapped[List["ChannelInventory"]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Store id={self.id} platform={self.platform} name={self.name!r} active={self.active}>"


# ========================================================================
# store_items —— 店铺 SKU 映射表（平台 SKU ↔ 内部 item）
# ========================================================================

class StoreItem(Base):
    __tablename__ = "store_items"
    __table_args__ = (
        UniqueConstraint("store_id", "pdd_sku_id", name="uq_store_items_store_pddsku"),
        UniqueConstraint("store_id", "item_id", name="uq_store_items_store_item"),
        Index("ix_store_items_store_item", "store_id", "item_id"),
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
    # 平台侧 SKU/外部编码（不同平台字段可复用 outer_id）
    pdd_sku_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    store: Mapped["Store"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<StoreItem id={self.id} store_id={self.store_id} item_id={self.item_id}>"


# ========================================================================
# channel_inventory —— 店铺 × 内部商品的渠道库存（A 策略）
# ========================================================================

class ChannelInventory(Base):
    __tablename__ = "channel_inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "item_id", name="uq_channel_inventory_store_item"),
        Index("ix_channel_inventory_store_item", "store_id", "item_id"),
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

    # A 策略参数：店铺粒度的配额上限（NULL 表示无限）
    cap_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 该店对该内品的占用合计（服务层维护）
    reserved_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 对平台可见量（服务层计算刷新：通常 min(physical - Σreserved, cap)）
    visible_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    store: Mapped["Store"] = relationship(back_populates="inventories")

    def __repr__(self) -> str:
        return (
            f"<ChannelInventory id={self.id} store_id={self.store_id} "
            f"item_id={self.item_id} visible={self.visible_qty} reserved={self.reserved_qty}>"
        )
