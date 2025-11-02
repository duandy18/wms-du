"""locations: fill code from name if NULL (compat trigger)

Revision ID: 20251031_locations_fill_code_trigger
Revises: 20251031_locations_add_code_and_uq
Create Date: 2025-10-31
"""

from alembic import op


revision = "20251031_locations_fill_code_trigger"
down_revision = "20251031_locations_add_code_and_uq"
branch_labels = None
depends_on = None


def upgrade():
    # 函数：若 NEW.code 为空，则用 NEW.name 回填
    op.execute(
        """
        CREATE OR REPLACE FUNCTION locations_fill_code()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.code IS NULL OR NEW.code = '' THEN
            NEW.code := NEW.name;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 触发器：INSERT 前执行
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname='trg_locations_fill_code'
          ) THEN
            CREATE TRIGGER trg_locations_fill_code
            BEFORE INSERT ON locations
            FOR EACH ROW
            EXECUTE FUNCTION locations_fill_code();
          END IF;
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname='trg_locations_fill_code'
          ) THEN
            DROP TRIGGER trg_locations_fill_code ON locations;
          END IF;
        END $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS locations_fill_code()")
