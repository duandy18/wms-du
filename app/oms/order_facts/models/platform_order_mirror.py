# app/oms/order_facts/models/platform_order_mirror.py
# Domain model: OMS-owned platform order mirrors imported from Collector export contracts.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class _MirrorMixin:
    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    collector_order_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    collector_store_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    collector_store_code: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    collector_store_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    wms_store_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
    )

    platform_order_no: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    platform_status: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    import_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="imported")
    mirror_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="active")

    source_updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    pulled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    collector_last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    receiver_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    amounts_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    platform_fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    raw_refs_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    imported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    last_synced_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class _MirrorLineMixin:
    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    collector_line_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    collector_order_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    platform_order_no: Mapped[str] = mapped_column(sa.String(128), nullable=False)

    merchant_sku: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    platform_item_id: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    platform_sku_id: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 4), nullable=False, server_default="0")
    unit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    line_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)

    platform_fields_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    raw_item_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class OmsPddOrderMirror(_MirrorMixin, Base):
    __tablename__ = "oms_pdd_order_mirrors"
    __table_args__ = (
        sa.UniqueConstraint("collector_order_id", name="uq_oms_pdd_order_mirrors_collector_order"),
        sa.UniqueConstraint(
            "collector_store_id",
            "platform_order_no",
            name="uq_oms_pdd_order_mirrors_collector_store_order",
        ),
        sa.CheckConstraint(
            "import_status IN ('imported', 'rejected', 'superseded')",
            name="ck_oms_pdd_order_mirrors_import_status",
        ),
        sa.CheckConstraint(
            "mirror_status IN ('active', 'archived')",
            name="ck_oms_pdd_order_mirrors_mirror_status",
        ),
        sa.Index("ix_oms_pdd_order_mirrors_order_no", "platform_order_no"),
        sa.Index("ix_oms_pdd_order_mirrors_status", "platform_status"),
        sa.Index("ix_oms_pdd_order_mirrors_wms_store", "wms_store_id"),
    )


class OmsPddOrderMirrorLine(_MirrorLineMixin, Base):
    __tablename__ = "oms_pdd_order_mirror_lines"
    __table_args__ = (
        sa.UniqueConstraint("mirror_id", "collector_line_id", name="uq_oms_pdd_order_mirror_lines_line"),
        sa.Index("ix_oms_pdd_order_mirror_lines_mirror", "mirror_id"),
        sa.Index("ix_oms_pdd_order_mirror_lines_merchant_sku", "merchant_sku"),
    )

    mirror_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("oms_pdd_order_mirrors.id", ondelete="CASCADE"),
        nullable=False,
    )


class OmsTaobaoOrderMirror(_MirrorMixin, Base):
    __tablename__ = "oms_taobao_order_mirrors"
    __table_args__ = (
        sa.UniqueConstraint("collector_order_id", name="uq_oms_taobao_order_mirrors_collector_order"),
        sa.UniqueConstraint(
            "collector_store_id",
            "platform_order_no",
            name="uq_oms_taobao_order_mirrors_collector_store_order",
        ),
        sa.CheckConstraint(
            "import_status IN ('imported', 'rejected', 'superseded')",
            name="ck_oms_taobao_order_mirrors_import_status",
        ),
        sa.CheckConstraint(
            "mirror_status IN ('active', 'archived')",
            name="ck_oms_taobao_order_mirrors_mirror_status",
        ),
        sa.Index("ix_oms_taobao_order_mirrors_order_no", "platform_order_no"),
        sa.Index("ix_oms_taobao_order_mirrors_status", "platform_status"),
        sa.Index("ix_oms_taobao_order_mirrors_wms_store", "wms_store_id"),
    )


class OmsTaobaoOrderMirrorLine(_MirrorLineMixin, Base):
    __tablename__ = "oms_taobao_order_mirror_lines"
    __table_args__ = (
        sa.UniqueConstraint("mirror_id", "collector_line_id", name="uq_oms_taobao_order_mirror_lines_line"),
        sa.Index("ix_oms_taobao_order_mirror_lines_mirror", "mirror_id"),
        sa.Index("ix_oms_taobao_order_mirror_lines_merchant_sku", "merchant_sku"),
    )

    mirror_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("oms_taobao_order_mirrors.id", ondelete="CASCADE"),
        nullable=False,
    )


class OmsJdOrderMirror(_MirrorMixin, Base):
    __tablename__ = "oms_jd_order_mirrors"
    __table_args__ = (
        sa.UniqueConstraint("collector_order_id", name="uq_oms_jd_order_mirrors_collector_order"),
        sa.UniqueConstraint(
            "collector_store_id",
            "platform_order_no",
            name="uq_oms_jd_order_mirrors_collector_store_order",
        ),
        sa.CheckConstraint(
            "import_status IN ('imported', 'rejected', 'superseded')",
            name="ck_oms_jd_order_mirrors_import_status",
        ),
        sa.CheckConstraint(
            "mirror_status IN ('active', 'archived')",
            name="ck_oms_jd_order_mirrors_mirror_status",
        ),
        sa.Index("ix_oms_jd_order_mirrors_order_no", "platform_order_no"),
        sa.Index("ix_oms_jd_order_mirrors_status", "platform_status"),
        sa.Index("ix_oms_jd_order_mirrors_wms_store", "wms_store_id"),
    )


class OmsJdOrderMirrorLine(_MirrorLineMixin, Base):
    __tablename__ = "oms_jd_order_mirror_lines"
    __table_args__ = (
        sa.UniqueConstraint("mirror_id", "collector_line_id", name="uq_oms_jd_order_mirror_lines_line"),
        sa.Index("ix_oms_jd_order_mirror_lines_mirror", "mirror_id"),
        sa.Index("ix_oms_jd_order_mirror_lines_merchant_sku", "merchant_sku"),
    )

    mirror_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("oms_jd_order_mirrors.id", ondelete="CASCADE"),
        nullable=False,
    )
