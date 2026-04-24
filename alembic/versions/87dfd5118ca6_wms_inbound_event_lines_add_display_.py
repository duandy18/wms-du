"""wms_inbound_event_lines_add_display_snapshots

Revision ID: 87dfd5118ca6
Revises: deb61de57b7b
Create Date: 2026-04-24 10:31:26.562704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "87dfd5118ca6"
down_revision: Union[str, Sequence[str], None] = "deb61de57b7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inbound_event_lines",
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_event_lines",
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "inbound_event_lines",
        sa.Column("actual_uom_name_snapshot", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("inbound_event_lines", "actual_uom_name_snapshot")
    op.drop_column("inbound_event_lines", "item_spec_snapshot")
    op.drop_column("inbound_event_lines", "item_name_snapshot")
