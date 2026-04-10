"""pms suppliers allow updating code

Revision ID: fc982b78117a
Revises: d810ee4649c6
Create Date: 2026-04-10 19:00:35.830447

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fc982b78117a"
down_revision: Union[str, Sequence[str], None] = "d810ee4649c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow suppliers.code to be updated.

    Keep DB truth as:
    - code is UNIQUE
    - code is NONBLANK
    - code is TRIMMED
    - code is UPPERCASE
    Only remove the immutable trigger/function.
    """
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_suppliers_code_immutable ON suppliers;
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS trg_forbid_update_suppliers_code();
        """
    )


def downgrade() -> None:
    """Restore suppliers.code immutability trigger/function."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_forbid_update_suppliers_code()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.code IS DISTINCT FROM OLD.code THEN
                RAISE EXCEPTION 'suppliers.code is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_suppliers_code_immutable ON suppliers;
        CREATE TRIGGER trg_suppliers_code_immutable
        BEFORE UPDATE ON suppliers
        FOR EACH ROW
        EXECUTE FUNCTION trg_forbid_update_suppliers_code();
        """
    )
