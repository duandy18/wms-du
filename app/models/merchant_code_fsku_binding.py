# app/models/merchant_code_fsku_binding.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MerchantCodeFskuBinding(Base):
    """
    商家规格编码（merchant_code / filled_code）→ FSKU 的绑定表（current-only，一码一对一）。

    唯一域：platform + shop_id + merchant_code
    规则：
      - bind = upsert（同码覆盖）
      - unbind = delete
    """

    __tablename__ = "merchant_code_fsku_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)

    # ✅ 收敛：DB 是 TEXT，因此 ORM 必须是 str + Text
    shop_id: Mapped[str] = mapped_column(Text, nullable=False)

    merchant_code: Mapped[str] = mapped_column(String(128), nullable=False)

    fsku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fskus.id", ondelete="RESTRICT"), nullable=False
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "shop_id", "merchant_code", name="ux_mc_fsku_bindings_unique"),
        Index("ix_mc_fsku_bindings_lookup", "platform", "shop_id", "merchant_code"),
        Index("ix_mc_fsku_bindings_fsku_id", "fsku_id"),
    )
