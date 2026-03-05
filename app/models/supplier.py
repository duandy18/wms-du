# app/models/supplier.py
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
    inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.supplier_contact import SupplierContact


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_suppliers_name"),
        UniqueConstraint("code", name="uq_suppliers_code"),
        # 供应商 code 作为业务身份：人工输入，但必须规范化且不可为空白
        # 注意：这里声明 CHECK 约束，DB 侧仍需要通过 Alembic migration 实际落地。
        CheckConstraint("btrim(code) <> ''", name="ck_suppliers_code_nonblank"),
        CheckConstraint("code = upper(code)", name="ck_suppliers_code_upper"),
        # name 作为展示字段：不允许空白（避免 UI/报表出现“空名供应商”）
        CheckConstraint("btrim(name) <> ''", name="ck_suppliers_name_nonblank"),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 业务身份：创建时必须提供；创建后不可修改（模型层防线，DB 侧还会用 trigger 强制）
    code: Mapped[str] = mapped_column(String(64), nullable=False)

    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    contacts: Mapped[List[SupplierContact]] = relationship(
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
        """
        业务身份：人工输入，但一旦创建后不可修改。
        - 统一 trim + upper
        - 禁止空白
        - 对已持久化对象，禁止改 code（应用层防线）
        """
        if value is None:
            raise ValueError("supplier.code 不能为空")

        v = value.strip().upper()
        if v == "":
            raise ValueError("supplier.code 不能为空白")

        state = sa_inspect(self)
        # persistent：已落库对象；pending：新建未提交；transient：未关联 session
        if state.persistent:
            old = getattr(self, "code", None)
            if old is not None and v != old:
                raise ValueError("supplier.code 不允许修改（创建后不可变）")

        return v

    @validates("name")
    def _validate_name(self, _key: str, value: str) -> str:
        if value is None:
            raise ValueError("supplier.name 不能为空")
        v = value.strip()
        if v == "":
            raise ValueError("supplier.name 不能为空白")
        return v
