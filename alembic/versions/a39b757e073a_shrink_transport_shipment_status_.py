"""shrink_transport_shipment_status_contract

Revision ID: a39b757e073a
Revises: 1c3a5672cfba
Create Date: 2026-03-13 14:30:13.662629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a39b757e073a"
down_revision: Union[str, Sequence[str], None] = "1c3a5672cfba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "ck_transport_shipments_status_valid",
        "transport_shipments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transport_shipments_status_valid",
        "transport_shipments",
        "status IN ('IN_TRANSIT', 'DELIVERED', 'LOST', 'RETURNED')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_transport_shipments_status_valid",
        "transport_shipments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transport_shipments_status_valid",
        "transport_shipments",
        "status IN ('PENDING', 'WAYBILL_REQUESTED', 'IN_TRANSIT', 'DELIVERED', 'FAILED', 'CANCELLED')",
    )
