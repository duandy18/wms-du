"""phase1a: make inbound_receipt_lines.batch_code nullable

Revision ID: cf7f038c35ff
Revises: 7ea2dbbec06d
Create Date: 2026-02-24 12:16:31.524557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf7f038c35ff'
down_revision: Union[str, Sequence[str], None] = '7ea2dbbec06d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Phase 1A:
    允许 inbound_receipt_lines.batch_code 为 NULL，
    为 batch_mode=NONE 提供合法存储语义，
    停止依赖 NOEXP / NONE 等伪批次占位。
    """
    op.alter_column(
        "inbound_receipt_lines",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema.

    回滚为 NOT NULL。
    若库中已有 NULL，将会失败。
    """
    op.alter_column(
        "inbound_receipt_lines",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
