"""receipt_lines: batch_code nullable + enforce null dates when no batch

Revision ID: 7ea2dbbec06d
Revises: e190c49aa0ee
Create Date: 2026-02-23 18:12:33.445697
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7ea2dbbec06d"
down_revision: Union[str, Sequence[str], None] = "e190c49aa0ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1️⃣ 允许 batch_code 为 NULL
    op.alter_column(
        "inbound_receipt_lines",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    # 2️⃣ 加结构守护：无批次时，不允许存在生产/效期
    op.create_check_constraint(
        constraint_name="ck_inbound_receipt_lines_batch_null_dates_null",
        table_name="inbound_receipt_lines",
        condition=(
            "(batch_code IS NOT NULL) "
            "OR (production_date IS NULL AND expiry_date IS NULL)"
        ),
    )


def downgrade() -> None:
    # ⚠️ 回滚前必须清理 NULL，否则 NOT NULL 会失败
    op.execute(
        """
        UPDATE inbound_receipt_lines
        SET batch_code = 'MIGRATION_RESTORE'
        WHERE batch_code IS NULL
        """
    )

    op.drop_constraint(
        "ck_inbound_receipt_lines_batch_null_dates_null",
        "inbound_receipt_lines",
        type_="check",
    )

    op.alter_column(
        "inbound_receipt_lines",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
