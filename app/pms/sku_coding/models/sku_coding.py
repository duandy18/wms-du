# app/pms/sku_coding/models/sku_coding.py
# SKU coding domain models: templates and template segments.
#
# 品牌 / 内部分类 / 属性预设选项已提升到 PMS 商品主数据：
# - pms_brands
# - pms_business_categories
# - item_attribute_defs
# - item_attribute_options
#
# SKU 编码域不再拥有属性词典，只负责 SKU 拼接模板。
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.pms.items.models.item_master import ItemAttributeDef


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
    attribute_def_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("item_attribute_defs.id", ondelete="RESTRICT"), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_multi_select: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    template: Mapped[SkuCodeTemplate] = relationship("SkuCodeTemplate", back_populates="segments", lazy="joined")
    attribute_def: Mapped[ItemAttributeDef | None] = relationship("ItemAttributeDef", lazy="joined")

    __table_args__ = (
        sa.CheckConstraint("source_type in ('BRAND', 'CATEGORY', 'ATTRIBUTE_OPTION', 'TEXT', 'SPEC')", name="ck_sku_code_template_segments_source_type"),
        sa.CheckConstraint(
            "((source_type = 'ATTRIBUTE_OPTION' and attribute_def_id is not null) or (source_type <> 'ATTRIBUTE_OPTION' and attribute_def_id is null))",
            name="ck_sku_code_template_segments_attribute_def",
        ),
        UniqueConstraint("template_id", "segment_key", name="uq_sku_code_template_segments_template_key"),
        sa.Index("ix_sku_code_template_segments_template_id", "template_id"),
        sa.Index("ix_sku_code_template_segments_attribute_def_id", "attribute_def_id"),
    )
