"""merge v2 unify+align heads

Revision ID: bca5b19ea75a
Revises: 20251111_v2_schema_unify_final, 20251111_v2_align_indexes_fk_and_types
Create Date: 2025-11-11 20:27:35.783155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bca5b19ea75a'
down_revision: Union[str, Sequence[str], None] = ('20251111_v2_schema_unify_final', '20251111_v2_align_indexes_fk_and_types')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
