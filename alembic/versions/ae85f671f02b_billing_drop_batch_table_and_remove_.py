"""billing: drop batch table and remove import_batch_id from reconciliations

Revision ID: ae85f671f02b
Revises: bd368177ca26
Create Date: 2026-03-18 12:44:38.130090
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae85f671f02b"
down_revision: Union[str, Sequence[str], None] = "bd368177ca26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 先删 shipping_record_reconciliations -> carrier_bill_import_batches 的 FK
    op.execute(
        """
        ALTER TABLE shipping_record_reconciliations
        DROP CONSTRAINT IF EXISTS fk_shipping_record_reconciliations_import_batch_id;
        """
    )

    # 2) 再删 carrier_bill_items -> carrier_bill_import_batches 的 FK
    op.execute(
        """
        ALTER TABLE carrier_bill_items
        DROP CONSTRAINT IF EXISTS fk_carrier_bill_items_import_batch_id;
        """
    )

    # 3) 删除 shipping_record_reconciliations 中的 import_batch_id 列
    op.drop_index(
        "ix_shipping_record_reconciliations_import_batch_id",
        table_name="shipping_record_reconciliations",
    )
    op.drop_index(
        "ix_shipping_record_reconciliations_batch_status",
        table_name="shipping_record_reconciliations",
    )
    op.drop_column("shipping_record_reconciliations", "import_batch_id")

    # 4) 补当前模型需要的索引
    op.create_index(
        "ix_shipping_record_reconciliations_carrier_status",
        "shipping_record_reconciliations",
        ["carrier_code", "status"],
        unique=False,
    )

    # 5) 最后删除 batch 表
    op.drop_table("carrier_bill_import_batches")


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复 batch 表
    op.create_table(
        "carrier_bill_import_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("carrier_code", sa.String(length=32), nullable=False),
        sa.Column("import_batch_no", sa.String(length=64), nullable=False),
        sa.Column("bill_month", sa.String(length=16), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="imported"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index(
        "ix_carrier_bill_import_batches_bill_month",
        "carrier_bill_import_batches",
        ["bill_month"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_bill_import_batches_imported_at",
        "carrier_bill_import_batches",
        ["imported_at"],
        unique=False,
    )
    op.create_index(
        "uq_carrier_bill_import_batches_carrier_batch",
        "carrier_bill_import_batches",
        ["carrier_code", "import_batch_no"],
        unique=True,
    )

    # 2) 删除当前索引
    op.drop_index(
        "ix_shipping_record_reconciliations_carrier_status",
        table_name="shipping_record_reconciliations",
    )

    # 3) 恢复 shipping_record_reconciliations.import_batch_id
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("import_batch_id", sa.BigInteger(), nullable=True),
    )

    op.create_index(
        "ix_shipping_record_reconciliations_import_batch_id",
        "shipping_record_reconciliations",
        ["import_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_shipping_record_reconciliations_batch_status",
        "shipping_record_reconciliations",
        ["import_batch_id", "status"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_shipping_record_reconciliations_import_batch_id",
        "shipping_record_reconciliations",
        "carrier_bill_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 4) 恢复 carrier_bill_items 的 FK（列本身由后续 5c migration 的 downgrade 恢复）
    op.create_foreign_key(
        "fk_carrier_bill_items_import_batch_id",
        "carrier_bill_items",
        "carrier_bill_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
