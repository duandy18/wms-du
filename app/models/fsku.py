# app/models/fsku.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Fsku(Base):
    __tablename__ = "fskus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ✅ 业务编码（全局唯一）：
    # DB 里是唯一索引（ux_fskus_code），这里用 Index(unique=True) 与之对齐，
    # 避免 alembic-check 误判需要新增 unique constraint。
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False)

    # ✅ 事实字段：商品形态（single/bundle）
    shape: Mapped[str] = mapped_column(String(20), nullable=False, server_default="bundle")

    # draft | published | retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    components: Mapped[list["FskuComponent"]] = relationship(
        back_populates="fsku",
        cascade="all, delete-orphan",
    )


class FskuComponent(Base):
    __tablename__ = "fsku_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    fsku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fskus.id", ondelete="CASCADE"), nullable=False, index=True
    )

    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    fsku: Mapped["Fsku"] = relationship(back_populates="components")


# 组件索引（你已有）
Index("ix_fsku_components_fsku_id", FskuComponent.fsku_id)
Index("ix_fsku_components_item_id", FskuComponent.item_id)

# ✅ 对齐 DB：唯一索引 ux_fskus_code
Index("ux_fskus_code", Fsku.code, unique=True)
