"""enforce shipping_providers.code not null (unique already exists)

Revision ID: 460104059fbd
Revises: 31286ad1e2df
Create Date: 2026-01-20 19:26:29.465371

"""
from typing import Sequence, Union

from alembic import op

revision: str = "460104059fbd"
down_revision: Union[str, Sequence[str], None] = "31286ad1e2df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    最终强约束（仅 NOT NULL）：
    - UNIQUE(code) 在仓库中已存在（uq_shipping_providers_code），这里不重复加。
    - 若仍存在 NULL，将直接抛错，逼“主数据治理”先完成。
    """
    # 1) 保险：trim；空串转 NULL
    op.execute(
        """
        UPDATE shipping_providers
           SET code = NULLIF(BTRIM(code), '')
         WHERE code IS NOT NULL
        """
    )

    # 2) 硬检查：不能还有 NULL
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM shipping_providers WHERE code IS NULL) THEN
            RAISE EXCEPTION 'cannot enforce NOT NULL: shipping_providers.code still has NULL values';
          END IF;
        END$$;
        """
    )

    # 3) NOT NULL
    op.execute("ALTER TABLE shipping_providers ALTER COLUMN code SET NOT NULL;")


def downgrade() -> None:
    op.execute("ALTER TABLE shipping_providers ALTER COLUMN code DROP NOT NULL;")
