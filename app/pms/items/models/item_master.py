# app/pms/items/models/item_master.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.items.models.item import Item


class PmsBrand(Base):
    __tablename__ = "pms_brands"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name_cn: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    code: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    is_locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    remark: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["Item"]] = relationship("Item", back_populates="brand_ref", lazy="selectin")

    __table_args__ = (
        sa.UniqueConstraint("name_cn", name="uq_pms_brands_name_cn"),
        sa.UniqueConstraint("code", name="uq_pms_brands_code"),
    )


class PmsBusinessCategory(Base):
    __tablename__ = "pms_business_categories"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("pms_business_categories.id", name="fk_pms_business_categories_parent", ondelete="RESTRICT"),
        nullable=True,
    )
    level: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    product_kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    category_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    category_code: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    path_code: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_leaf: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    is_locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    remark: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    parent: Mapped["PmsBusinessCategory | None"] = relationship(
        "PmsBusinessCategory",
        remote_side=[id],
        lazy="joined",
    )
    items: Mapped[list["Item"]] = relationship("Item", back_populates="category_ref", lazy="selectin")

    __table_args__ = (
        sa.CheckConstraint("level in (1, 2, 3)", name="ck_pms_business_categories_level"),
        sa.CheckConstraint(
            "product_kind in ('FOOD', 'SUPPLY', 'OTHER')",
            name="ck_pms_business_categories_product_kind",
        ),
        sa.UniqueConstraint("path_code", name="uq_pms_business_categories_path_code"),
        sa.UniqueConstraint("parent_id", "category_code", name="uq_pms_business_categories_parent_code"),
        sa.Index("ix_pms_business_categories_parent_id", "parent_id"),
        sa.Index("ix_pms_business_categories_product_kind", "product_kind"),
    )


class ItemAttributeDef(Base):
    __tablename__ = "item_attribute_defs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    name_cn: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    name_en: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    product_kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    value_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    selection_mode: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'SINGLE'"))
    unit: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    is_item_required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_sku_required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_sku_segment: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    is_locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    remark: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    options: Mapped[list["ItemAttributeOption"]] = relationship(
        "ItemAttributeOption",
        back_populates="attribute_def",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.CheckConstraint(
            "product_kind in ('FOOD', 'SUPPLY', 'OTHER', 'COMMON')",
            name="ck_item_attribute_defs_product_kind",
        ),
        sa.CheckConstraint(
            "value_type in ('TEXT', 'NUMBER', 'OPTION', 'BOOL')",
            name="ck_item_attribute_defs_value_type",
        ),
        sa.CheckConstraint(
            "selection_mode in ('SINGLE', 'MULTI')",
            name="ck_item_attribute_defs_selection_mode",
        ),
        sa.UniqueConstraint("product_kind", "code", name="uq_item_attribute_defs_product_kind_code"),
        sa.Index("ix_item_attribute_defs_product_kind", "product_kind"),
    )


class ItemAttributeOption(Base):
    __tablename__ = "item_attribute_options"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    attribute_def_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("item_attribute_defs.id", name="fk_item_attribute_options_def", ondelete="CASCADE"),
        nullable=False,
    )
    option_code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    option_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    is_locked: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attribute_def: Mapped[ItemAttributeDef] = relationship("ItemAttributeDef", back_populates="options", lazy="joined")

    __table_args__ = (
        sa.UniqueConstraint("attribute_def_id", "option_code", name="uq_item_attribute_options_def_code"),
        sa.Index("ix_item_attribute_options_def_id", "attribute_def_id"),
    )


class ItemAttributeValue(Base):
    __tablename__ = "item_attribute_values"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("items.id", name="fk_item_attribute_values_item", ondelete="CASCADE"),
        nullable=False,
    )
    attribute_def_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("item_attribute_defs.id", name="fk_item_attribute_values_def", ondelete="RESTRICT"),
        nullable=False,
    )
    value_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6), nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    value_option_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("item_attribute_options.id", name="fk_item_attribute_values_option", ondelete="RESTRICT"),
        nullable=True,
    )
    value_option_code_snapshot: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    value_unit_snapshot: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    item: Mapped["Item"] = relationship("Item", back_populates="attribute_values", lazy="joined")
    attribute_def: Mapped[ItemAttributeDef] = relationship("ItemAttributeDef", lazy="joined")
    option: Mapped[ItemAttributeOption | None] = relationship("ItemAttributeOption", lazy="joined")

    __table_args__ = (
        sa.Index(
            "uq_item_attribute_values_item_def_scalar",
            "item_id",
            "attribute_def_id",
            unique=True,
            postgresql_where=sa.text("value_option_id IS NULL"),
        ),
        sa.Index(
            "uq_item_attribute_values_item_def_option",
            "item_id",
            "attribute_def_id",
            "value_option_id",
            unique=True,
            postgresql_where=sa.text("value_option_id IS NOT NULL"),
        ),
        sa.Index("ix_item_attribute_values_item_id", "item_id"),
        sa.Index("ix_item_attribute_values_def_id", "attribute_def_id"),
    )
