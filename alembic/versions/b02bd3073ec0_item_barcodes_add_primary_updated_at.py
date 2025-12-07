"""item_barcodes add primary + updated_at

Revision ID: b02bd3073ec0
Revises: d406745e34a3
Create Date: 2025-12-02 15:54:31.734305
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b02bd3073ec0'
down_revision: Union[str, Sequence[str], None] = 'd406745e34a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema:
    - add column is_primary BOOLEAN NOT NULL DEFAULT false
    - add updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    - add partial unique index on (item_id) where is_primary = true
    """
    op.add_column(
        "item_barcodes",
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.add_column(
        "item_barcodes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # PostgreSQL partial unique index
    op.create_index(
        "uq_item_barcodes_primary",
        "item_barcodes",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )


def downgrade() -> None:
    """
    Downgrade:
    - drop unique index
    - drop added columns
    """
    op.drop_index("uq_item_barcodes_primary", table_name="item_barcodes")

    op.drop_column("item_barcodes", "updated_at")
    op.drop_column("item_barcodes", "is_primary")
