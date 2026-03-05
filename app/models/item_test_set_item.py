# app/models/item_test_set_item.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.item_test_set import ItemTestSet


class ItemTestSetItem(Base):
    __tablename__ = "item_test_set_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 与 d95f7d97126f 保持一致：set_id/item_id 都是 BigInteger
    set_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("item_test_sets.id", ondelete="CASCADE"),
        nullable=False,
    )

    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    test_set: Mapped["ItemTestSet"] = relationship(
        "ItemTestSet",
        back_populates="items",
    )

    __table_args__ = (
        UniqueConstraint("set_id", "item_id", name="uq_item_test_set_items_set_id_item_id"),
        Index("ix_item_test_set_items_item_id", "item_id"),
        Index("ix_item_test_set_items_set_id", "set_id"),
    )
