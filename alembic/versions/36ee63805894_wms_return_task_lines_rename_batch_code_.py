"""wms_return_task_lines_rename_batch_code_to_lot_code_snapshot

Revision ID: 36ee63805894
Revises: c896df82c17c
Create Date: 2026-04-25

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "36ee63805894"
down_revision: Union[str, Sequence[str], None] = "c896df82c17c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename return task lot display snapshot to lot_code_snapshot."""

    op.alter_column(
        "return_task_lines",
        "batch_code",
        new_column_name="lot_code_snapshot",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        existing_comment="展示快照：来自原出库 lot 的 lots.lot_code；不参与结构锚点",
        comment="展示快照：来自原出库 lot 的 lots.lot_code；不参与结构锚点",
    )


def downgrade() -> None:
    """Restore previous return task display snapshot column name."""

    op.alter_column(
        "return_task_lines",
        "lot_code_snapshot",
        new_column_name="batch_code",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        existing_comment="展示快照：来自原出库 lot 的 lots.lot_code；不参与结构锚点",
        comment="展示快照：来自原出库 lot 的 lots.lot_code；不参与结构锚点",
    )
