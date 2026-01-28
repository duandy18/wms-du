"""feat(pricing): add zone segment_template_id

Revision ID: f92578cb0ef4
Revises: a8235d7af4f7
Create Date: 2026-01-27 19:42:31.935982
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f92578cb0ef4"
down_revision: Union[str, Sequence[str], None] = "a8235d7af4f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add optional segment_template_id to shipping_provider_zones.

    Semantics:
    - NULL: zone uses scheme default segment structure (legacy-compatible)
    - NOT NULL: zone explicitly binds to a segment template
    """

    # 1) add column
    op.add_column(
        "shipping_provider_zones",
        sa.Column("segment_template_id", sa.Integer(), nullable=True),
    )

    # 2) foreign key -> shipping_provider_pricing_scheme_segment_templates.id
    op.create_foreign_key(
        "fk_sp_zones_segment_template_id",
        "shipping_provider_zones",
        "shipping_provider_pricing_scheme_segment_templates",
        ["segment_template_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 3) index for lookup / filtering
    op.create_index(
        "ix_sp_zones_segment_template_id",
        "shipping_provider_zones",
        ["segment_template_id"],
        unique=False,
    )


def downgrade() -> None:
    # reverse order
    op.drop_index(
        "ix_sp_zones_segment_template_id",
        table_name="shipping_provider_zones",
    )
    op.drop_constraint(
        "fk_sp_zones_segment_template_id",
        "shipping_provider_zones",
        type_="foreignkey",
    )
    op.drop_column("shipping_provider_zones", "segment_template_id")
