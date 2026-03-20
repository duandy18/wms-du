"""fix: shorten pricing template index names

Revision ID: 819c6fec1439
Revises: 02a284d9351c
Create Date: 2026-03-20 17:42:01.688444
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "819c6fec1439"
down_revision: Union[str, Sequence[str], None] = "02a284d9351c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ranges
    op.execute(
        "DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_module_ranges_template_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_spptmr_template_id")
    op.create_index(
        "ix_spptmr_template_id",
        "shipping_provider_pricing_template_module_ranges",
        ["template_id"],
    )

    # groups
    op.execute(
        "DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_destination_groups_template_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_spptdg_template_id")
    op.create_index(
        "ix_spptdg_template_id",
        "shipping_provider_pricing_template_destination_groups",
        ["template_id"],
    )

    # matrix
    op.execute(
        "DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_matrix_group_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_spptm_group_id")
    op.create_index(
        "ix_spptm_group_id",
        "shipping_provider_pricing_template_matrix",
        ["group_id"],
    )


def downgrade() -> None:
    # matrix
    op.execute("DROP INDEX IF EXISTS ix_spptm_group_id")
    op.execute("DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_matrix_group_id")
    op.create_index(
        "ix_shipping_provider_pricing_template_matrix_group_id",
        "shipping_provider_pricing_template_matrix",
        ["group_id"],
    )

    # groups
    op.execute("DROP INDEX IF EXISTS ix_spptdg_template_id")
    op.execute(
        "DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_destination_groups_template_id"
    )
    op.create_index(
        "ix_shipping_provider_pricing_template_destination_groups_template_id",
        "shipping_provider_pricing_template_destination_groups",
        ["template_id"],
    )

    # ranges
    op.execute("DROP INDEX IF EXISTS ix_spptmr_template_id")
    op.execute(
        "DROP INDEX IF EXISTS ix_shipping_provider_pricing_template_module_ranges_template_id"
    )
    op.create_index(
        "ix_shipping_provider_pricing_template_module_ranges_template_id",
        "shipping_provider_pricing_template_module_ranges",
        ["template_id"],
    )
