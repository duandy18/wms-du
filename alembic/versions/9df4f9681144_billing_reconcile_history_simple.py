"""billing_reconcile_history_simple

Revision ID: 9df4f9681144
Revises: 7053c668a3cb
Create Date: 2026-03-19 13:45:54.824924

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9df4f9681144"
down_revision: Union[str, Sequence[str], None] = "7053c668a3cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "shipping_bill_reconciliation_histories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("carrier_bill_item_id", sa.BigInteger(), nullable=False),
        sa.Column("shipping_record_id", sa.BigInteger(), nullable=True),
        sa.Column("carrier_code", sa.String(length=32), nullable=False),
        sa.Column("tracking_no", sa.String(length=128), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("weight_diff_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("cost_diff", sa.Numeric(12, 2), nullable=True),
        sa.Column("adjust_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("approved_reason_text", sa.Text(), nullable=True),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["carrier_bill_item_id"],
            ["carrier_bill_items.id"],
            name="fk_shipping_bill_reconciliation_histories_carrier_bill_item_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shipping_record_id"],
            ["shipping_records.id"],
            name="fk_shipping_bill_reconciliation_histories_shipping_record_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "carrier_bill_item_id",
            name="uq_shipping_bill_reconciliation_histories_bill_item_id",
        ),
        sa.CheckConstraint(
            "result_status IN ('matched', 'approved_bill_only', 'resolved')",
            name="ck_shipping_bill_reconciliation_histories_result_status",
        ),
    )
    op.create_index(
        "ix_shipping_bill_reconciliation_histories_tracking_no",
        "shipping_bill_reconciliation_histories",
        ["tracking_no"],
        unique=False,
    )
    op.create_index(
        "ix_shipping_bill_reconciliation_histories_carrier_tracking",
        "shipping_bill_reconciliation_histories",
        ["carrier_code", "tracking_no"],
        unique=False,
    )

    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("approved_reason_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        INSERT INTO shipping_bill_reconciliation_histories (
            carrier_bill_item_id,
            shipping_record_id,
            carrier_code,
            tracking_no,
            result_status,
            weight_diff_kg,
            cost_diff,
            adjust_amount,
            approved_reason_text,
            archived_at
        )
        SELECT
            r.carrier_bill_item_id,
            r.shipping_record_id,
            r.carrier_code,
            r.tracking_no,
            'approved_bill_only',
            r.weight_diff_kg,
            r.cost_diff,
            r.adjust_amount,
            NULL,
            r.created_at
        FROM shipping_record_reconciliations r
        WHERE r.status = 'bill_only'
          AND r.carrier_bill_item_id IS NOT NULL
        """
    )

    op.execute(
        """
        DELETE FROM shipping_record_reconciliations
        WHERE status = 'record_only'
        """
    )

    op.drop_constraint(
        "ck_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "ck_shipping_record_reconciliations_status_shape",
        "shipping_record_reconciliations",
        type_="check",
    )

    op.create_check_constraint(
        "ck_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        "status IN ('diff', 'bill_only')",
    )
    op.create_check_constraint(
        "ck_shipping_record_reconciliations_status_shape",
        "shipping_record_reconciliations",
        """
        (
          (status = 'diff' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NOT NULL)
          OR
          (status = 'bill_only' AND shipping_record_id IS NULL AND carrier_bill_item_id IS NOT NULL)
        )
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "ck_shipping_record_reconciliations_status_shape",
        "shipping_record_reconciliations",
        type_="check",
    )

    op.create_check_constraint(
        "ck_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        "status IN ('diff', 'bill_only', 'record_only')",
    )
    op.create_check_constraint(
        "ck_shipping_record_reconciliations_status_shape",
        "shipping_record_reconciliations",
        """
        (
          (status = 'diff' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NOT NULL)
          OR
          (status = 'bill_only' AND shipping_record_id IS NULL AND carrier_bill_item_id IS NOT NULL)
          OR
          (status = 'record_only' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NULL)
        )
        """,
    )

    op.execute(
        """
        INSERT INTO shipping_record_reconciliations (
            shipping_record_id,
            carrier_bill_item_id,
            tracking_no,
            weight_diff_kg,
            cost_diff,
            created_at,
            adjust_amount,
            status,
            carrier_code
        )
        SELECT
            h.shipping_record_id,
            h.carrier_bill_item_id,
            h.tracking_no,
            h.weight_diff_kg,
            h.cost_diff,
            h.archived_at,
            h.adjust_amount,
            'bill_only',
            h.carrier_code
        FROM shipping_bill_reconciliation_histories h
        WHERE h.result_status = 'approved_bill_only'
        """
    )

    op.drop_column("shipping_record_reconciliations", "approved_at")
    op.drop_column("shipping_record_reconciliations", "approved_reason_text")

    op.drop_index(
        "ix_shipping_bill_reconciliation_histories_carrier_tracking",
        table_name="shipping_bill_reconciliation_histories",
    )
    op.drop_index(
        "ix_shipping_bill_reconciliation_histories_tracking_no",
        table_name="shipping_bill_reconciliation_histories",
    )
    op.drop_table("shipping_bill_reconciliation_histories")
