"""shipping_providers: enforce code immutability and trim

Revision ID: 328e9ca43399
Revises: cd98745db32a
Create Date: 2026-03-03 17:42:55.935636
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "328e9ca43399"
down_revision: Union[str, Sequence[str], None] = "cd98745db32a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1️⃣ 加 trim CHECK（防止首尾空格漂移）
    op.execute(
        """
        ALTER TABLE shipping_providers
        ADD CONSTRAINT ck_shipping_providers_code_trimmed
        CHECK (code = btrim(code));
        """
    )

    # 2️⃣ 创建不可变 trigger 函数
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_forbid_update_shipping_providers_code()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.code IS DISTINCT FROM OLD.code THEN
            RAISE EXCEPTION 'shipping_providers.code is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    # 3️⃣ 绑定 trigger
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_shipping_providers_code_immutable ON shipping_providers;

        CREATE TRIGGER trg_shipping_providers_code_immutable
        BEFORE UPDATE ON shipping_providers
        FOR EACH ROW
        EXECUTE FUNCTION trg_forbid_update_shipping_providers_code();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_shipping_providers_code_immutable ON shipping_providers;
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS trg_forbid_update_shipping_providers_code();
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_providers
        DROP CONSTRAINT IF EXISTS ck_shipping_providers_code_trimmed;
        """
    )
