"""pol make locator not null

Phase N+4 hardening (final lock):
- Ensure locator_kind/locator_value are backfilled (defensive for test DB rebuilds)
- Then enforce NOT NULL
- Add explicit pairing check for clarity

Revision ID: 6f3449b2ca0b
Revises: 23c0b5d2c9e8
Create Date: 2026-02-10 11:59:26.127891
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6f3449b2ca0b"
down_revision: Union[str, Sequence[str], None] = "23c0b5d2c9e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) Defensive backfill (for dev-test-db rebuilds / older seed states)
    #    - prefer filled_code when present
    #    - fallback to line_no
    op.execute(
        """
        UPDATE platform_order_lines
           SET locator_kind  = CASE
                                WHEN filled_code IS NOT NULL AND btrim(filled_code) <> ''
                                  THEN 'FILLED_CODE'
                                ELSE 'LINE_NO'
                              END,
               locator_value = CASE
                                WHEN filled_code IS NOT NULL AND btrim(filled_code) <> ''
                                  THEN filled_code
                                ELSE (line_no::text)
                              END
         WHERE locator_kind IS NULL
            OR btrim(locator_kind) = ''
            OR locator_value IS NULL
            OR btrim(locator_value) = '';
        """
    )

    # 1) Enforce NOT NULL on semantic locator columns
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ALTER COLUMN locator_kind SET NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ALTER COLUMN locator_value SET NOT NULL;
        """
    )

    # 2) Add explicit pairing constraint (idempotent via catalog check)
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname = 'ck_pol_locator_pairing'
          ) THEN
            ALTER TABLE platform_order_lines
            ADD CONSTRAINT ck_pol_locator_pairing
            CHECK (
              locator_kind IN ('FILLED_CODE', 'LINE_NO')
              AND btrim(locator_value) <> ''
            );
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Rollback pairing constraint
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_pairing;
        """
    )

    # Rollback NOT NULL (restore nullable state)
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ALTER COLUMN locator_value DROP NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ALTER COLUMN locator_kind DROP NOT NULL;
        """
    )
