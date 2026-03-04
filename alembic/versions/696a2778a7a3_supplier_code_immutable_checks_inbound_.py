"""supplier: code immutable + checks; inbound_receipts supplier fk restrict

Revision ID: 696a2778a7a3
Revises: f3990b69f1bd
Create Date: 2026-03-03 16:38:47.087770
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "696a2778a7a3"
down_revision: Union[str, Sequence[str], None] = "f3990b69f1bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1) suppliers: 强化 code / name 约束（规范化 + 非空白）
    # ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE suppliers
        ADD CONSTRAINT ck_suppliers_code_nonblank
        CHECK (btrim(code) <> '');
        """
    )

    op.execute(
        """
        ALTER TABLE suppliers
        ADD CONSTRAINT ck_suppliers_code_upper
        CHECK (code = upper(code));
        """
    )

    op.execute(
        """
        ALTER TABLE suppliers
        ADD CONSTRAINT ck_suppliers_name_nonblank
        CHECK (btrim(name) <> '');
        """
    )

    # ---------------------------------------------------------
    # 2) suppliers: code 创建后不可修改（DB 级不可变）
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # 3) inbound_receipts: 收敛删除语义（SET NULL -> RESTRICT）
    # ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE inbound_receipts
        DROP CONSTRAINT IF EXISTS fk_inbound_receipts_supplier;
        """
    )

    op.execute(
        """
        ALTER TABLE inbound_receipts
        ADD CONSTRAINT fk_inbound_receipts_supplier
        FOREIGN KEY (supplier_id)
        REFERENCES suppliers(id)
        ON DELETE RESTRICT;
        """
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # 3) inbound_receipts: 恢复 SET NULL
    # ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE inbound_receipts
        DROP CONSTRAINT IF EXISTS fk_inbound_receipts_supplier;
        """
    )

    op.execute(
        """
        ALTER TABLE inbound_receipts
        ADD CONSTRAINT fk_inbound_receipts_supplier
        FOREIGN KEY (supplier_id)
        REFERENCES suppliers(id)
        ON DELETE SET NULL;
        """
    )

    # ---------------------------------------------------------
    # 2) 删除 trigger + function
    # ---------------------------------------------------------
    op.execute(
        "DROP TRIGGER IF EXISTS trg_suppliers_code_immutable ON suppliers;"
    )

    op.execute(
        "DROP FUNCTION IF EXISTS trg_forbid_update_suppliers_code();"
    )

    # ---------------------------------------------------------
    # 1) 删除 CHECK 约束
    # ---------------------------------------------------------
    op.execute(
        "ALTER TABLE suppliers DROP CONSTRAINT IF EXISTS ck_suppliers_name_nonblank;"
    )

    op.execute(
        "ALTER TABLE suppliers DROP CONSTRAINT IF EXISTS ck_suppliers_code_upper;"
    )

    op.execute(
        "ALTER TABLE suppliers DROP CONSTRAINT IF EXISTS ck_suppliers_code_nonblank;"
    )
