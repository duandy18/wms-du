"""audit_events: add (category,ref,created_at) index

Revision ID: 7a9c9bfbf3af
Revises: 2270f45da74d
Create Date: 2025-11-07 13:01:34.149285
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision: str = "7a9c9bfbf3af"
down_revision: Union[str, Sequence[str], None] = "2270f45da74d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "ix_audit_events_cat_ref_time"
_TABLE = "audit_events"


def upgrade() -> None:
    """Upgrade schema: create composite index for faster OUTBOUND audit queries."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 若索引不存在则创建
    exists = any(ix["name"] == _INDEX for ix in insp.get_indexes(_TABLE))
    if not exists:
        op.create_index(_INDEX, _TABLE, ["category", "ref", "created_at"])
        print(f"[MIGRATION] Created index {_INDEX} on {_TABLE}(category,ref,created_at)")
    else:
        print(f"[MIGRATION] Index {_INDEX} already exists, skipped.")


def downgrade() -> None:
    """Downgrade schema: drop composite index."""
    op.drop_index(_INDEX, table_name=_TABLE, if_exists=True)
