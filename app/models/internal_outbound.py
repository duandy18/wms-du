from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InternalOutboundDoc(Base):
  __tablename__ = "internal_outbound_docs"

  id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
  warehouse_id: Mapped[int] = mapped_column(
      BigInteger, ForeignKey("warehouses.id"), nullable=False
  )
  doc_no: Mapped[str] = mapped_column(Text, nullable=False)
  doc_type: Mapped[str] = mapped_column(Text, nullable=False)  # SAMPLE_OUT / INTERNAL_USE / SCRAP ...
  status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")

  # 领取人信息
  recipient_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  recipient_id: Mapped[Optional[int]] = mapped_column(
      BigInteger, ForeignKey("users.id"), nullable=True
  )
  recipient_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  recipient_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

  # 备注 / 审计
  note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  created_by: Mapped[Optional[int]] = mapped_column(
      BigInteger, ForeignKey("users.id"), nullable=True
  )
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), nullable=False
  )
  confirmed_by: Mapped[Optional[int]] = mapped_column(
      BigInteger, ForeignKey("users.id"), nullable=True
  )
  confirmed_at: Mapped[Optional[datetime]] = mapped_column(
      DateTime(timezone=True), nullable=True
  )
  canceled_by: Mapped[Optional[int]] = mapped_column(
      BigInteger, ForeignKey("users.id"), nullable=True
  )
  canceled_at: Mapped[Optional[datetime]] = mapped_column(
      DateTime(timezone=True), nullable=True
  )

  # trace / 扩展
  trace_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  extra_meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

  # 关系
  warehouse = relationship("Warehouse", backref="internal_outbound_docs")
  recipient = relationship(
      "User",
      foreign_keys=[recipient_id],
      backref="received_internal_outbound_docs",
  )
  created_by_user = relationship(
      "User",
      foreign_keys=[created_by],
      backref="created_internal_outbound_docs",
  )
  confirmed_by_user = relationship(
      "User",
      foreign_keys=[confirmed_by],
      backref="confirmed_internal_outbound_docs",
  )
  canceled_by_user = relationship(
      "User",
      foreign_keys=[canceled_by],
      backref="canceled_internal_outbound_docs",
  )

  lines: Mapped[list["InternalOutboundLine"]] = relationship(
      "InternalOutboundLine",
      back_populates="doc",
      cascade="all, delete-orphan",
      lazy="selectin",
  )


class InternalOutboundLine(Base):
  __tablename__ = "internal_outbound_lines"

  id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
  doc_id: Mapped[int] = mapped_column(
      BigInteger, ForeignKey("internal_outbound_docs.id"), nullable=False
  )
  line_no: Mapped[int] = mapped_column(Integer, nullable=False)
  item_id: Mapped[int] = mapped_column(
      BigInteger, ForeignKey("items.id"), nullable=False
  )
  batch_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  requested_qty: Mapped[int] = mapped_column(Integer, nullable=False)
  confirmed_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
  uom: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
  extra_meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

  doc: Mapped["InternalOutboundDoc"] = relationship(
      "InternalOutboundDoc", back_populates="lines"
  )
  item = relationship("Item", backref="internal_outbound_lines")
