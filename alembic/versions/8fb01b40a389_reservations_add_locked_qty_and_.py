"""reservations add locked_qty and released_at for lifecycle

Revision ID: 8fb01b40a389
Revises: 3d473566713c
Create Date: 2025-11-08 07:42:13.020059
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "8fb01b40a389"
down_revision: Union[str, Sequence[str], None] = "3d473566713c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("""
    DO $$
    BEGIN
      -- locked_qty: 已锁定数量，默认0，非空
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='locked_qty'
      ) THEN
        ALTER TABLE reservations
          ADD COLUMN locked_qty INTEGER DEFAULT 0 NOT NULL;
      END IF;

      -- released_at: 释放时间，可空
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='released_at'
      ) THEN
        ALTER TABLE reservations
          ADD COLUMN released_at TIMESTAMPTZ;
      END IF;
    END $$;
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='locked_qty'
      ) THEN
        ALTER TABLE reservations DROP COLUMN locked_qty;
      END IF;

      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='released_at'
      ) THEN
        ALTER TABLE reservations DROP COLUMN released_at;
      END IF;
    END $$;
    """)
    )
