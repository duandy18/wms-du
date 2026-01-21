"""guard shipping_providers.code normalize (trim) without new unique

Revision ID: 31286ad1e2df
Revises: 0209d301e96c
Create Date: 2026-01-20 19:25:37.659820

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31286ad1e2df"
down_revision: Union[str, Sequence[str], None] = "0209d301e96c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    说明：
    - 仓库中已存在 uq_shipping_providers_code（UNIQUE(code)），无需重复创建。
    - 本迁移只做轻量数据整形，确保“空白/空串”不会混入：
      - trim
      - '' -> NULL
    """
    op.execute(
        """
        UPDATE shipping_providers
           SET code = NULLIF(BTRIM(code), '')
         WHERE code IS NOT NULL
        """
    )


def downgrade() -> None:
    # 数据整形不可逆；downgrade 选择 no-op
    pass
