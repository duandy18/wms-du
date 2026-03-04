"""warehouses: code normalized + immutable

Revision ID: fa3efdb244b5
Revises: 7976c71f1506
Create Date: 2026-03-03 16:50:32.117277
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fa3efdb244b5"
down_revision: Union[str, Sequence[str], None] = "7976c71f1506"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 0) 先补齐历史数据：TEST/seed 可能存在 code=NULL 或空白
    #    - 采用 WH-<id> 作为稳定且唯一的默认编码
    #    - 然后统一 upper，确保满足 ck_warehouses_code_upper
    # ---------------------------------------------------------
    op.execute(
        """
        UPDATE warehouses
           SET code = 'WH-' || id::text
         WHERE code IS NULL
            OR btrim(code) = '';

        UPDATE warehouses
           SET code = upper(code)
         WHERE code IS NOT NULL
           AND code <> upper(code);
        """
    )

    # ---------------------------------------------------------
    # 1) code 规范化约束（防漂移）
    # ---------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_warehouses_code_nonblank') THEN
            ALTER TABLE warehouses
            ADD CONSTRAINT ck_warehouses_code_nonblank
            CHECK (btrim(code) <> '');
          END IF;

          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_warehouses_code_upper') THEN
            ALTER TABLE warehouses
            ADD CONSTRAINT ck_warehouses_code_upper
            CHECK (code = upper(code));
          END IF;

          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_warehouses_code_trimmed') THEN
            ALTER TABLE warehouses
            ADD CONSTRAINT ck_warehouses_code_trimmed
            CHECK (code = btrim(code));
          END IF;
        END $$;
        """
    )

    # ---------------------------------------------------------
    # 2) code NOT NULL（现在数据已被补齐，不会再触发 NotNullViolation）
    # ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE warehouses
        ALTER COLUMN code SET NOT NULL;
        """
    )

    # ---------------------------------------------------------
    # 3) code 不可变（DB 级）
    # ---------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_forbid_update_warehouses_code()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.code IS DISTINCT FROM OLD.code THEN
            RAISE EXCEPTION 'warehouses.code is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_warehouses_code_immutable ON warehouses;

        CREATE TRIGGER trg_warehouses_code_immutable
        BEFORE UPDATE ON warehouses
        FOR EACH ROW
        EXECUTE FUNCTION trg_forbid_update_warehouses_code();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_warehouses_code_immutable ON warehouses;")
    op.execute("DROP FUNCTION IF EXISTS trg_forbid_update_warehouses_code();")

    op.execute("ALTER TABLE warehouses ALTER COLUMN code DROP NOT NULL;")

    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_trimmed;")
    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_upper;")
    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_nonblank;")
