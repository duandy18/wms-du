from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(Integer, ForeignKey("warehouses.id"), nullable=False)

    # DB 仍保留的 code 列（如后续不需要再发迁移删除）
    code: Mapped[str] = mapped_column(Text, nullable=False)

    warehouse = relationship("Warehouse", lazy="selectin")

    __table_args__ = (
        Index("ix_locations_warehouse_id", "warehouse_id"),
        Index("ix_locations_wh", "warehouse_id"),
        {"info": {"skip_autogen": True}},
    )
