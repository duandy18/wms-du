# app/models/shipping_provider_surcharge.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShippingProviderSurcharge(Base):
    __tablename__ = "shipping_provider_surcharges"
    __table_args__ = (UniqueConstraint("scheme_id", "name", name="uq_sp_surcharges_scheme_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scheme_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_provider_pricing_schemes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # 条件表达式：{"dest":{"city":["北京市"]}} / {"flag_any":["irregular"]} ...
    condition_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # 金额表达式：{"kind":"flat","amount":1.5} / {"kind":"per_kg","rate":0.5} ...
    amount_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    scheme = relationship("ShippingProviderPricingScheme", back_populates="surcharges")

    def __repr__(self) -> str:
        return f"<ShippingProviderSurcharge id={self.id} scheme_id={self.scheme_id} name={self.name!r}>"
