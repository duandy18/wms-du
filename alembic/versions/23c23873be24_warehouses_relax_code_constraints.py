"""warehouses: relax code constraints

Revision ID: 23c23873be24
Revises: 15547a554fe0
Create Date: 2026-03-03 19:26:29.103495
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "23c23873be24"
down_revision: Union[str, Sequence[str], None] = "15547a554fe0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    降级 warehouses.code 约束：
    - 取消 NOT NULL
    - 删除不可变 trigger
    - 删除 code 规范化 CHECK 约束
    """

    # 1) 取消 NOT NULL
    op.execute(
        """
        ALTER TABLE warehouses
        ALTER COLUMN code DROP NOT NULL;
        """
    )

    # 2) 删除不可变 trigger
    op.execute("DROP TRIGGER IF EXISTS trg_warehouses_code_immutable ON warehouses;")
    op.execute("DROP FUNCTION IF EXISTS trg_forbid_update_warehouses_code();")

    # 3) 删除 code 强治理 CHECK 约束
    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_trimmed;")
    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_upper;")
    op.execute("ALTER TABLE warehouses DROP CONSTRAINT IF EXISTS ck_warehouses_code_nonblank;")


def downgrade() -> None:
    """
    恢复强约束（仅结构恢复，不保证历史数据满足）
    """

    # 1) 恢复 CHECK
    op.execute(
        """
        ALTER TABLE warehouses
        ADD CONSTRAINT ck_warehouses_code_nonblank
        CHECK (btrim(code) <> '');
        """
    )

    op.execute(
        """
        ALTER TABLE warehouses
        ADD CONSTRAINT ck_warehouses_code_upper
        CHECK (code = upper(code));
        """
    )

    op.execute(
        """
        ALTER TABLE warehouses
        ADD CONSTRAINT ck_warehouses_code_trimmed
        CHECK (code = btrim(code));
        """
    )

    # 2) 恢复 NOT NULL
    op.execute(
        """
        ALTER TABLE warehouses
        ALTER COLUMN code SET NOT NULL;
        """
    )

    # 3) 恢复不可变 trigger
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
        CREATE TRIGGER trg_warehouses_code_immutable
        BEFORE UPDATE ON warehouses
        FOR EACH ROW
        EXECUTE FUNCTION trg_forbid_update_warehouses_code();
        """
    )
