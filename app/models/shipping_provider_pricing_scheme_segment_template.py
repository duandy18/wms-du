# app/models/shipping_provider_pricing_scheme_segment_template.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderPricingSchemeSegmentTemplate(Base):
    __tablename__ = "shipping_provider_pricing_scheme_segment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # draft / published / archived
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    # ✅ 多活允许：同一 scheme 可存在多条 is_active=true（互斥已移除）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ✅ 关键：显式 foreign_keys，避免与 scheme.default_segment_template_id 形成两条 FK 路径导致歧义
    scheme = relationship(
        "ShippingProviderPricingScheme",
        back_populates="segment_templates",
        lazy="selectin",
        foreign_keys=[scheme_id],
    )

    items = relationship(
        "ShippingProviderPricingSchemeSegmentTemplateItem",
        back_populates="template",
        lazy="selectin",
        order_by="ShippingProviderPricingSchemeSegmentTemplateItem.ord.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SchemeSegmentTemplate id={self.id} scheme_id={self.scheme_id} status={self.status} active={self.is_active}>"
