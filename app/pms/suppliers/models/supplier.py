# app/pms/suppliers/models/supplier.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.suppliers.models.supplier_contact import SupplierContact


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_suppliers_name"),
        UniqueConstraint("code", name="uq_suppliers_code"),
        CheckConstraint("btrim(code) <> ''", name="ck_suppliers_code_nonblank"),
        CheckConstraint("code = btrim(code)", name="ck_suppliers_code_trimmed"),
        CheckConstraint("code = upper(code)", name="ck_suppliers_code_upper"),
        CheckConstraint("btrim(name) <> ''", name="ck_suppliers_name_nonblank"),
        CheckConstraint("name = btrim(name)", name="ck_suppliers_name_trimmed"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    contacts: Mapped[List["SupplierContact"]] = relationship(
        "SupplierContact",
        back_populates="supplier",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @validates("code")
    def _validate_code(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("supplier.code 不能为空")

        v = value.strip().upper()
        if v == "":
            raise ValueError("supplier.code 不能为空白")

        return v

    @validates("name")
    def _validate_name(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("supplier.name 不能为空")
        v = value.strip()
        if v == "":
            raise ValueError("supplier.name 不能为空白")
        return v
