"""add analytics to page_registry domain_code

Revision ID: 43f4fd19527e
Revises: d97dd0feb8fa
Create Date: 2026-04-07 11:36:20.204490

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "43f4fd19527e"
down_revision: Union[str, Sequence[str], None] = "d97dd0feb8fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        type_="check",
    )
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('analytics', 'oms', 'pms', 'procurement', 'wms', 'tms', 'admin')",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        type_="check",
    )
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('oms', 'pms', 'procurement', 'wms', 'tms', 'admin')",
    )
