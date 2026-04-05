# alembic/versions/4e00dcea9213_de_role_permissions_fix_suppliers_.py
"""de_role_permissions_fix_suppliers_domain_to_pms

Revision ID: 4e00dcea9213
Revises: 62378c84f1e9
Create Date: 2026-04-05 16:33:15.220223

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4e00dcea9213"
down_revision: Union[str, Sequence[str], None] = "62378c84f1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE page_registry
           SET domain_code = 'pms'
         WHERE code = 'wms.masterdata.suppliers'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE page_registry
           SET domain_code = 'procurement'
         WHERE code = 'wms.masterdata.suppliers'
        """
    )
