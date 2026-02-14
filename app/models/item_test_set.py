# app/models/item_test_set.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.item_test_set_item import ItemTestSetItem


class ItemTestSet(Base):
    __tablename__ = "item_test_sets"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    items: Mapped[List["ItemTestSetItem"]] = relationship(
        "ItemTestSetItem",
        back_populates="test_set",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_item_test_sets_code", "code"),
    )
