"""shipping_records package_no comment align

Revision ID: f9199b55771b
Revises: 0c00db920758
Create Date: 2026-03-25 20:04:03.345374

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f9199b55771b"
down_revision: Union[str, Sequence[str], None] = "0c00db920758"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COMMENT = "包裹序号，从 1 开始，对应 order_shipment_prepare_packages.package_no"
_OLD_COMMENT = "包裹序号，从 1 开始"


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "shipping_records",
        "package_no",
        existing_type=None,
        comment=_NEW_COMMENT,
        existing_comment=_OLD_COMMENT,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "shipping_records",
        "package_no",
        existing_type=None,
        comment=_OLD_COMMENT,
        existing_comment=_NEW_COMMENT,
    )
