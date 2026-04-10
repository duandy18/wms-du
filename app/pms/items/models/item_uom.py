# app/pms/items/models/item_uom.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.items.models.item import Item


class ItemUOM(Base):
    """
    item_uoms：商品多包装/多单位结构化（Phase M-2）

    语义：
    - 一个 item 可以有多个 uom（PCS/箱/盒/...）
    - ratio_to_base：1 uom = ratio_to_base * base_uom（base_uom 真相源 = item_uoms.is_base）
    - is_base：每个 item 恰好一个 base（用 partial unique index 强制）
    - net_weight_kg：净重（kg）。基础包装为真相源；非基础包装默认可按 ratio_to_base 推导；不含包材。

    Phase M-5（二阶段）：
    - 强化默认单位唯一性（purchase/inbound/outbound）——DB 用 partial unique index 强制
    """

    __tablename__ = "item_uoms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", name="fk_item_uoms_item", ondelete="RESTRICT"),
        nullable=False,
    )

    # 单位编码/名称（允许自定义），如 PCS / CASE / BOX / 袋 / 箱
    uom: Mapped[str] = mapped_column(String(16), nullable=False)

    # 1 uom = ratio_to_base * base_uom（base_uom 真相源 = item_uoms.is_base）
    ratio_to_base: Mapped[int] = mapped_column(Integer, nullable=False)

    # 展示名（可选）：如“箱”“盒”
    display_name: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # 净重（kg）。基础包装为真相源；非基础包装默认可按 ratio_to_base 推导；不含包材。
    net_weight_kg: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="净重（kg）。基础包装为真相源；非基础包装默认可按 ratio_to_base 推导；不含包材。",
    )

    is_base: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    is_purchase_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    is_inbound_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    is_outbound_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

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

    item: Mapped["Item"] = relationship(
        "Item",
        back_populates="uoms",
        lazy="selectin",
        overlaps="uoms",
    )

    __table_args__ = (
        sa.UniqueConstraint("item_id", "uom", name="uq_item_uoms_item_uom"),
        CheckConstraint("ratio_to_base >= 1", name="ck_item_uoms_ratio_ge_1"),
        Index(
            "uq_item_uoms_one_base_per_item",
            "item_id",
            unique=True,
            postgresql_where=text("is_base = true"),
        ),
        Index(
            "uq_item_uoms_one_purchase_default_per_item",
            "item_id",
            unique=True,
            postgresql_where=text("is_purchase_default = true"),
        ),
        Index(
            "uq_item_uoms_one_inbound_default_per_item",
            "item_id",
            unique=True,
            postgresql_where=text("is_inbound_default = true"),
        ),
        Index(
            "uq_item_uoms_one_outbound_default_per_item",
            "item_id",
            unique=True,
            postgresql_where=text("is_outbound_default = true"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ItemUOM id={self.id} item_id={self.item_id} "
            f"uom={self.uom!r} ratio_to_base={self.ratio_to_base} "
            f"net_weight_kg={self.net_weight_kg} "
            f"is_base={self.is_base}>"
        )
