"""20251201_add_batch_code_to_pick_task_lines

Revision ID: f2e764aaa449
Revises: c7cc84014612
Create Date: 2025-12-01 18:08:24.814159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2e764aaa449"
down_revision: Union[str, Sequence[str], None] = "c7cc84014612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add batch_code column to pick_task_lines.
    """
    op.add_column(
        "pick_task_lines",
        sa.Column("batch_code", sa.Text(), nullable=True),
    )

    # 如后续需要，可以加索引（暂不强制，避免无谓的负担）
    # op.create_index(
    #     "ix_pick_task_lines_item_batch",
    #     "pick_task_lines",
    #     ["item_id", "batch_code"],
    # )


def downgrade() -> None:
    """
    Drop batch_code column.
    """
    # 如果上面建了索引，这里要先 drop:
    # op.drop_index("ix_pick_task_lines_item_batch", table_name="pick_task_lines")

    op.drop_column("pick_task_lines", "batch_code")
