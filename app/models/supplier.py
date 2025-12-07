# app/models/supplier.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Supplier(Base):
    """
    供应商主数据（Phase 1）

    - name: 公司名称（必填，唯一）
    - code: 供应商编码（可选，唯一，如 SUP-001）
    - contact_name: 联系人姓名
    - phone: 联系电话（手机 / 座机）
    - email: 电子邮件
    - wechat: 微信号
    - active: 是否启用
    """

    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_suppliers_name"),
        UniqueConstraint("code", name="uq_suppliers_code"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wechat: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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

    def __repr__(self) -> str:
        return f"<Supplier id={self.id} name={self.name!r} active={self.active}>"
