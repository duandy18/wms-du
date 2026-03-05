"""remove_receive_task_fk_from_inbound_receipts

Revision ID: f444321b4e0b
Revises: 5621e0cd65e6
Create Date: 2026-02-17 22:10:56.575730

删除 inbound_receipts.receive_task_id 外键与列。
本迁移不可逆。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f444321b4e0b"
down_revision: Union[str, Sequence[str], None] = "5621e0cd65e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    删除 inbound_receipts.receive_task_id 外键与列。
    """

    # 删除外键约束（名称可能不同，建议先 \d inbound_receipts 确认）
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_type = 'FOREIGN KEY'
                  AND table_name = 'inbound_receipts'
                  AND constraint_name = 'inbound_receipts_receive_task_id_fkey'
            ) THEN
                ALTER TABLE inbound_receipts
                DROP CONSTRAINT inbound_receipts_receive_task_id_fkey;
            END IF;
        END
        $$;
        """
    )

    # 删除列
    op.execute(
        """
        ALTER TABLE inbound_receipts
        DROP COLUMN IF EXISTS receive_task_id;
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "Irreversible migration: receive_task_id was permanently removed from inbound_receipts."
    )
