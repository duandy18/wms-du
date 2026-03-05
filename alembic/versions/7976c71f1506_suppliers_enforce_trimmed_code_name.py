"""suppliers: enforce trimmed code/name

Revision ID: 7976c71f1506
Revises: 696a2778a7a3
Create Date: 2026-03-03 16:44:47.448712
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7976c71f1506"
down_revision: Union[str, Sequence[str], None] = "696a2778a7a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 禁止首尾空格导致的“隐形漂移”
    # code / name 必须等于其 btrim 结果
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'ck_suppliers_code_trimmed'
          ) THEN
            ALTER TABLE suppliers
            ADD CONSTRAINT ck_suppliers_code_trimmed
            CHECK (code = btrim(code));
          END IF;

          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'ck_suppliers_name_trimmed'
          ) THEN
            ALTER TABLE suppliers
            ADD CONSTRAINT ck_suppliers_name_trimmed
            CHECK (name = btrim(name));
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE suppliers
        DROP CONSTRAINT IF EXISTS ck_suppliers_name_trimmed;
        """
    )

    op.execute(
        """
        ALTER TABLE suppliers
        DROP CONSTRAINT IF EXISTS ck_suppliers_code_trimmed;
        """
    )
