"""billing reconciliation add anomaly statuses

Revision ID: 4e086e9148ec
Revises: 28a7dbaef752
Create Date: 2026-03-17 17:08:53.814974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4e086e9148ec"
down_revision: Union[str, Sequence[str], None] = "28a7dbaef752"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("carrier_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("import_batch_no", sa.String(length=64), nullable=True),
    )

    # 旧数据全是 diff-only 记录，先补回基础字段。
    # 这里用相关子查询，避免 PostgreSQL UPDATE ... FROM 对目标表别名引用的坑。
    op.execute(
        """
        UPDATE shipping_record_reconciliations r
        SET
          status = 'diff',
          carrier_code = COALESCE(
            (
              SELECT b.carrier_code
              FROM carrier_bill_items b
              WHERE b.id = r.carrier_bill_item_id
            ),
            (
              SELECT s.carrier_code
              FROM shipping_records s
              WHERE s.id = r.shipping_record_id
            )
          ),
          import_batch_no = (
            SELECT b.import_batch_no
            FROM carrier_bill_items b
            WHERE b.id = r.carrier_bill_item_id
          )
        """
    )

    # 如果回填后仍有空值，直接失败，避免后续 NOT NULL 静悄悄埋雷。
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM shipping_record_reconciliations
            WHERE status IS NULL
               OR carrier_code IS NULL
               OR import_batch_no IS NULL
          ) THEN
            RAISE EXCEPTION
              'shipping_record_reconciliations backfill produced NULLs for status/carrier_code/import_batch_no';
          END IF;
        END $$;
        """
    )

    op.alter_column(
        "shipping_record_reconciliations",
        "status",
        existing_type=sa.String(length=16),
        nullable=False,
    )
    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_code",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "shipping_record_reconciliations",
        "import_batch_no",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.alter_column(
        "shipping_record_reconciliations",
        "shipping_record_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    op.drop_constraint(
        "uq_shipping_record_reconciliations_shipping_record_id",
        "shipping_record_reconciliations",
        type_="unique",
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

    op.create_index(
        "uq_shipping_record_reconciliations_shipping_record_id_notnull",
        "shipping_record_reconciliations",
        ["shipping_record_id"],
        unique=True,
        postgresql_where=sa.text("shipping_record_id IS NOT NULL"),
    )

    op.create_index(
        "uq_shipping_record_reconciliations_bill_item_id_notnull",
        "shipping_record_reconciliations",
        ["carrier_bill_item_id"],
        unique=True,
        postgresql_where=sa.text("carrier_bill_item_id IS NOT NULL"),
    )

    op.create_index(
        "ix_shipping_record_reconciliations_carrier_batch_status",
        "shipping_record_reconciliations",
        ["carrier_code", "import_batch_no", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_shipping_record_reconciliations_carrier_batch_status",
        table_name="shipping_record_reconciliations",
    )
    op.drop_index(
        "uq_shipping_record_reconciliations_bill_item_id_notnull",
        table_name="shipping_record_reconciliations",
    )
    op.drop_index(
        "uq_shipping_record_reconciliations_shipping_record_id_notnull",
        table_name="shipping_record_reconciliations",
    )

    op.drop_constraint(
        "ck_shipping_record_reconciliations_status_shape",
        "shipping_record_reconciliations",
        type_="check",
    )
    op.drop_constraint(
        "ck_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        type_="check",
    )

    op.create_unique_constraint(
        "uq_shipping_record_reconciliations_shipping_record_id",
        "shipping_record_reconciliations",
        ["shipping_record_id"],
    )

    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "shipping_record_reconciliations",
        "shipping_record_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.drop_column("shipping_record_reconciliations", "import_batch_no")
    op.drop_column("shipping_record_reconciliations", "carrier_code")
    op.drop_column("shipping_record_reconciliations", "status")
