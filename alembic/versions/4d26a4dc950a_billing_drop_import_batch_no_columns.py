"""billing_drop_import_batch_no_columns

Revision ID: 4d26a4dc950a
Revises: cda36a44ec26
Create Date: 2026-03-18 14:48:53.716261
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d26a4dc950a"
down_revision: Union[str, Sequence[str], None] = "cda36a44ec26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    删除 billing 体系中 import_batch_no 字段
    """

    # 1️⃣ carrier_bill_items
    # 先删索引（如果存在）
    op.execute("DROP INDEX IF EXISTS ix_carrier_bill_items_batch_no;")

    # 再删列
    with op.batch_alter_table("carrier_bill_items") as batch_op:
        batch_op.drop_column("import_batch_no")

    # 2️⃣ shipping_record_reconciliations
    # 这个表没有单独索引，但旧 migration 可能建过组合索引，防御性处理
    op.execute(
        """
        DROP INDEX IF EXISTS ix_shipping_record_reconciliations_carrier_batch_status;
        """
    )

    with op.batch_alter_table("shipping_record_reconciliations") as batch_op:
        batch_op.drop_column("import_batch_no")


def downgrade() -> None:
    """
    回滚：恢复 import_batch_no 字段（仅结构，不恢复数据语义）
    """

    # 1️⃣ carrier_bill_items
    with op.batch_alter_table("carrier_bill_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "import_batch_no",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )

    op.create_index(
        "ix_carrier_bill_items_batch_no",
        "carrier_bill_items",
        ["import_batch_no"],
        unique=False,
    )

    # 2️⃣ shipping_record_reconciliations
    with op.batch_alter_table("shipping_record_reconciliations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "import_batch_no",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )

    # 恢复旧组合索引（如果你还需要）
    op.create_index(
        "ix_shipping_record_reconciliations_carrier_batch_status",
        "shipping_record_reconciliations",
        ["carrier_code", "import_batch_no", "status"],
        unique=False,
    )
