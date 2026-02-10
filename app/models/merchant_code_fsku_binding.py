# app/models/merchant_code_fsku_binding.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MerchantCodeFskuBinding(Base):
    """
    商家规格编码（merchant_code / filled_code）→ FSKU 的 time-ranged 绑定表（current 用 effective_to IS NULL 表示）。

    唯一域：platform + shop_id + merchant_code
    规则：同一时刻（current）只能绑定一个 FSKU；切换绑定通过关闭旧 current 再插入新 current。
    """

    __tablename__ = "merchant_code_fsku_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[int] = mapped_column(Integer, nullable=False)

    merchant_code: Mapped[str] = mapped_column(String(128), nullable=False)

    fsku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fskus.id", ondelete="RESTRICT"), nullable=False
    )

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_mc_fsku_bindings_lookup",
            "platform",
            "shop_id",
            "merchant_code",
            "effective_to",
        ),
        Index("ix_mc_fsku_bindings_fsku_id", "fsku_id"),
    )
