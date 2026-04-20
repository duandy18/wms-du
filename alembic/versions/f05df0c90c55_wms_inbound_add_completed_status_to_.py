"""wms_inbound_add_completed_status_to_inbound_receipts

Revision ID: f05df0c90c55
Revises: d75f3fa5b346
Create Date: 2026-04-20 18:21:58.723174

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f05df0c90c55"
down_revision: Union[str, Sequence[str], None] = "d75f3fa5b346"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "ck_inbound_receipts_status",
        "inbound_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_inbound_receipts_status",
        "inbound_receipts",
        "status IN ('DRAFT', 'RELEASED', 'COMPLETED', 'VOIDED')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_inbound_receipts_status",
        "inbound_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_inbound_receipts_status",
        "inbound_receipts",
        "status IN ('DRAFT', 'RELEASED', 'VOIDED')",
    )
