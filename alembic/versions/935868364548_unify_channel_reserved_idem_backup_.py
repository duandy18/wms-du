"""unify channel_reserved_idem_backup_20251109 timestamp

Revision ID: 935868364548
Revises: 391c76dee630
Create Date: 2025-11-15 23:06:23.468058

将 channel_reserved_idem_backup_20251109.created_at
从 timestamp without time zone 统一为 timestamptz（UTC 语义）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "935868364548"
down_revision: Union[str, Sequence[str], None] = "391c76dee630"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    sql = """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'channel_reserved_idem_backup_20251109'
              AND column_name = 'created_at'
              AND data_type = 'timestamp without time zone'
        ) THEN
            ALTER TABLE channel_reserved_idem_backup_20251109
                ALTER COLUMN created_at
                TYPE timestamptz
                USING created_at AT TIME ZONE 'UTC';
        END IF;
    END
    $$;
    """
    op.execute(sa.text(sql))


def downgrade() -> None:
    """Downgrade schema."""

    sql = """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'channel_reserved_idem_backup_20251109'
              AND column_name = 'created_at'
              AND data_type = 'timestamp with time zone'
        ) THEN
            ALTER TABLE channel_reserved_idem_backup_20251109
                ALTER COLUMN created_at
                TYPE timestamp
                USING created_at AT TIME ZONE 'UTC';
        END IF;
    END
    $$;
    """
    op.execute(sa.text(sql))
