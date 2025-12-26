# app/models/shipping_provider_pricing_scheme_segment.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeSegment(Base):
    __tablename__ = "shipping_provider_pricing_scheme_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 方案内顺序（列顺序）
    ord: Mapped[int] = mapped_column(Integer, nullable=False)

    # min/max：数值型真相（max 为空表示 ∞）
    min_kg: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)

    # ✅ 每段启停（你要的核心能力）
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    scheme = relationship("ShippingProviderPricingScheme", back_populates="segments", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PricingSchemeSegment id={self.id} scheme_id={self.scheme_id} ord={self.ord} min={self.min_kg} max={self.max_kg} active={self.active}>"
