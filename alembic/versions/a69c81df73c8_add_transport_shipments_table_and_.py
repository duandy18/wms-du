"""add transport shipments table and shipping record shipment_id

Revision ID: a69c81df73c8
Revises: 04aa7e1aa68b
Create Date: 2026-03-13 11:47:51.504727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a69c81df73c8"
down_revision: Union[str, Sequence[str], None] = "04aa7e1aa68b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # transport_shipments 主实体表
    # ------------------------------------------------------------------
    op.create_table(
        "transport_shipments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_ref", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),
        sa.Column("quote_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("receiver_name", sa.String(length=128), nullable=True),
        sa.Column("receiver_phone", sa.String(length=64), nullable=True),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("district", sa.String(length=64), nullable=True),
        sa.Column("address_detail", sa.String(length=255), nullable=True),
        sa.Column("tracking_no", sa.String(length=128), nullable=True),
        sa.Column("carrier_code", sa.String(length=32), nullable=True),
        sa.Column("carrier_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_transport_shipments_warehouse_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shipping_provider_id"],
            ["shipping_providers.id"],
            name="fk_transport_shipments_provider_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="transport_shipments_pkey"),
        sa.UniqueConstraint(
            "platform",
            "shop_id",
            "order_ref",
            name="uq_transport_shipments_platform_shop_ref",
        ),
        sa.CheckConstraint(
            "weight_kg > 0",
            name="ck_transport_shipments_weight_kg_positive",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'WAYBILL_REQUESTED', 'IN_TRANSIT', 'DELIVERED', 'FAILED', 'CANCELLED')",
            name="ck_transport_shipments_status_valid",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(quote_snapshot) = 'object'",
            name="ck_transport_shipments_quote_snapshot_object",
        ),
        sa.CheckConstraint(
            "(error_code IS NULL AND error_message IS NULL) OR (error_code IS NOT NULL)",
            name="ck_transport_shipments_error_pair",
        ),
    )

    op.create_index(
        "ix_transport_shipments_trace_id",
        "transport_shipments",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_provider_id",
        "transport_shipments",
        ["shipping_provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_warehouse_id",
        "transport_shipments",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_status",
        "transport_shipments",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_delivery_time",
        "transport_shipments",
        ["delivery_time"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_created_at",
        "transport_shipments",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_transport_shipments_ref_time",
        "transport_shipments",
        ["order_ref", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_transport_shipments_provider_tracking_notnull",
        "transport_shipments",
        ["shipping_provider_id", "tracking_no"],
        unique=True,
        postgresql_where=sa.text("tracking_no IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # shipping_records 增加 shipment_id，降级为 ledger / projection
    # ------------------------------------------------------------------
    op.add_column(
        "shipping_records",
        sa.Column("shipment_id", sa.BigInteger(), nullable=True),
    )

    op.create_foreign_key(
        "fk_shipping_records_shipment_id",
        "shipping_records",
        "transport_shipments",
        ["shipment_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_shipping_records_shipment_id",
        "shipping_records",
        ["shipment_id"],
        unique=False,
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 回滚 shipping_records 改造
    # ------------------------------------------------------------------
    op.drop_index("ix_shipping_records_shipment_id", table_name="shipping_records")
    op.drop_constraint(
        "fk_shipping_records_shipment_id",
        "shipping_records",
        type_="foreignkey",
    )
    op.drop_column("shipping_records", "shipment_id")

    # ------------------------------------------------------------------
    # 回滚 transport_shipments 主实体表
    # ------------------------------------------------------------------
    op.drop_index("uq_transport_shipments_provider_tracking_notnull", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_ref_time", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_created_at", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_delivery_time", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_status", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_warehouse_id", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_provider_id", table_name="transport_shipments")
    op.drop_index("ix_transport_shipments_trace_id", table_name="transport_shipments")
    op.drop_table("transport_shipments")
