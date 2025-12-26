# app/models/shipping_provider_pricing_scheme_segment_template_item.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeSegmentTemplateItem(Base):
    __tablename__ = "shipping_provider_pricing_scheme_segment_template_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_scheme_segment_templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    ord: Mapped[int] = mapped_column(Integer, nullable=False)

    min_kg: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    max_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)  # NULL = ∞

    # 段级启停：发布后仍允许切换（不允许改 min/max/ord）
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    template = relationship("ShippingProviderPricingSchemeSegmentTemplate", back_populates="items", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TemplateItem id={self.id} tpl={self.template_id} ord={self.ord} min={self.min_kg} max={self.max_kg} active={self.active}>"
