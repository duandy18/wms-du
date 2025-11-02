# app/models/party.py
from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import Enum, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PartyType(enum.Enum):
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    BOTH = "both"


class Party(Base):
    """
    往来单位（供应商/客户/两者）
    说明：
    - 与原表结构保持一致：name 可为空（历史兼容），email 可空且唯一。
    - 显式索引/唯一约束，查询更稳。
    - 不新增列、无需 Alembic 迁移。
    """
    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("email", name="uq_parties_email"),
        UniqueConstraint("name", name="uq_parties_name"),
        Index("ix_parties_name", "name"),
        Index("ix_parties_type", "party_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 兼容历史：允许 NULL
    party_type: Mapped[PartyType] = mapped_column(Enum(PartyType), nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 唯一约束见上
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<Party id={self.id!r} name={self.name!r} type={self.party_type.value}>"
