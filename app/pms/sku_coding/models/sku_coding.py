# app/pms/sku_coding/models/sku_coding.py
# SKU coding domain models: term dictionaries, templates and template segments.
#
# 品牌 / 内部分类已提升到 PMS 商品主数据：
# - pms_brands
# - pms_business_categories
#
# SKU 编码域不再拥有品牌 / 分类表，只引用 PMS 主数据。
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class SkuCodeTermGroup(Base):
    __tablename__ = "sku_code_term_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    group_code: Mapped[str] = mapped_column(String(32), nullable=False)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_multi_select: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    terms: Mapped[list["SkuCodeTerm"]] = relationship("SkuCodeTerm", back_populates="group", lazy="selectin")

    __table_args__ = (
        sa.CheckConstraint("product_kind in ('FOOD', 'SUPPLY', 'COMMON')", name="ck_sku_code_term_groups_product_kind"),
        UniqueConstraint("product_kind", "group_code", name="uq_sku_code_term_groups_kind_code"),
    )


class SkuCodeTerm(Base):
    __tablename__ = "sku_code_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("sku_code_term_groups.id", ondelete="RESTRICT"), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    group: Mapped[SkuCodeTermGroup] = relationship("SkuCodeTermGroup", back_populates="terms", lazy="joined")
    aliases: Mapped[list["SkuCodeTermAlias"]] = relationship("SkuCodeTermAlias", back_populates="term", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("group_id", "name_cn", name="uq_sku_code_terms_group_name_cn"),
        UniqueConstraint("group_id", "code", name="uq_sku_code_terms_group_code"),
        sa.Index("ix_sku_code_terms_group_id", "group_id"),
    )


class SkuCodeTermAlias(Base):
    __tablename__ = "sku_code_term_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(Integer, ForeignKey("sku_code_terms.id", ondelete="CASCADE"), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    term: Mapped[SkuCodeTerm] = relationship("SkuCodeTerm", back_populates="aliases", lazy="joined")

    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_sku_code_term_aliases_normalized"),
        sa.Index("ix_sku_code_term_aliases_term_id", "term_id"),
    )


class SkuCodeTemplate(Base):
    __tablename__ = "sku_code_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'SKU'"))
    separator: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'-'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    segments: Mapped[list["SkuCodeTemplateSegment"]] = relationship("SkuCodeTemplateSegment", back_populates="template", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        sa.CheckConstraint("product_kind in ('FOOD', 'SUPPLY')", name="ck_sku_code_templates_product_kind"),
        UniqueConstraint("template_code", name="uq_sku_code_templates_template_code"),
    )


class SkuCodeTemplateSegment(Base):
    __tablename__ = "sku_code_template_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("sku_code_templates.id", ondelete="CASCADE"), nullable=False)
    segment_key: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    term_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sku_code_term_groups.id", ondelete="RESTRICT"), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_multi_select: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    template: Mapped[SkuCodeTemplate] = relationship("SkuCodeTemplate", back_populates="segments", lazy="joined")
    term_group: Mapped[SkuCodeTermGroup | None] = relationship("SkuCodeTermGroup", lazy="joined")

    __table_args__ = (
        sa.CheckConstraint("source_type in ('BRAND', 'CATEGORY', 'TERM', 'TEXT', 'SPEC')", name="ck_sku_code_template_segments_source_type"),
        UniqueConstraint("template_id", "segment_key", name="uq_sku_code_template_segments_template_key"),
        sa.Index("ix_sku_code_template_segments_template_id", "template_id"),
    )
