# app/tms/pricing/templates/models/shipping_provider_pricing_template_validation_record.py
# Domain move: pricing template validation ORM belongs to TMS pricing templates.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingProviderPricingTemplateValidationRecord(Base):
    __tablename__ = "shipping_provider_pricing_template_validation_records"
    __table_args__ = (
        Index(
            "ix_sppt_validation_records_template_id",
            "template_id",
        ),
        Index(
            "ix_sppt_validation_records_operator_user_id",
            "operator_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    operator_user_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingProviderPricingTemplateValidationRecord id={self.id} "
            f"template_id={self.template_id} "
            f"operator_user_id={self.operator_user_id}>"
        )
