"""drop order_fulfillment override and blocked_detail

Revision ID: e9eaa9d713c5
Revises: ea8e69d8e270
Create Date: 2026-02-04 15:14:25.817730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9eaa9d713c5"
down_revision: Union[str, Sequence[str], None] = "ea8e69d8e270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("order_fulfillment") as batch_op:
        batch_op.drop_column("blocked_detail")
        batch_op.drop_column("overridden_by")
        batch_op.drop_column("overridden_at")
        batch_op.drop_column("override_reason")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("order_fulfillment") as batch_op:
        batch_op.add_column(sa.Column("override_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("overridden_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("blocked_detail", sa.Text(), nullable=True))
