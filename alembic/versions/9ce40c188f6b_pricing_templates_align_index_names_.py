"""pricing_templates: align index names with model

Revision ID: 9ce40c188f6b
Revises: 90f913d15180
Create Date: 2026-03-21 17:13:39.044331

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9ce40c188f6b"
down_revision: Union[str, Sequence[str], None] = "90f913d15180"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_pricing_templates"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_sppt_shipping_provider_id")
    op.execute("DROP INDEX IF EXISTS ix_sppt_status")
    op.execute("DROP INDEX IF EXISTS ix_sppt_validation_status")

    op.execute(
        f"CREATE INDEX IF NOT EXISTS "
        f"ix_shipping_provider_pricing_templates_shipping_provider_id "
        f"ON {TABLE} (shipping_provider_id)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS "
        f"ix_shipping_provider_pricing_templates_status "
        f"ON {TABLE} (status)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS "
        f"ix_shipping_provider_pricing_templates_validation_status "
        f"ON {TABLE} (validation_status)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_shipping_provider_pricing_templates_shipping_provider_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_shipping_provider_pricing_templates_status"
    )
    op.execute(
        "DROP INDEX IF EXISTS "
        "ix_shipping_provider_pricing_templates_validation_status"
    )

    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_sppt_shipping_provider_id "
        f"ON {TABLE} (shipping_provider_id)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_sppt_status "
        f"ON {TABLE} (status)"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_sppt_validation_status "
        f"ON {TABLE} (validation_status)"
    )
