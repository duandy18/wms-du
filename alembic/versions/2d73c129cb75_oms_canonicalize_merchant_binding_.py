"""oms canonicalize merchant binding platform codes

Revision ID: 2d73c129cb75
Revises: 202604281620
Create Date: 2026-04-28 18:51:58.243733

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2d73c129cb75"
down_revision: Union[str, Sequence[str], None] = "202604281620"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Canonicalize merchant-code binding platform codes."""

    # 先删除小写平台码中已经有大写等价记录的重复行，避免 UPDATE 触发唯一约束冲突。
    op.execute(
        """
        DELETE FROM merchant_code_fsku_bindings lower_b
        USING merchant_code_fsku_bindings upper_b
        WHERE lower_b.id <> upper_b.id
          AND lower_b.platform IN ('pdd', 'taobao', 'jd')
          AND upper_b.platform = upper(lower_b.platform)
          AND upper_b.store_code = lower_b.store_code
          AND upper_b.merchant_code = lower_b.merchant_code
        """
    )

    # 再把剩余小写平台码统一为 OMS 业务事实平台码。
    op.execute(
        """
        UPDATE merchant_code_fsku_bindings
           SET platform = upper(platform),
               updated_at = now()
         WHERE platform IN ('pdd', 'taobao', 'jd')
        """
    )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for platform-code canonicalization."""

    # 这是业务事实收口迁移：PDD / TAOBAO / JD 是终态平台码。
    # 不能可靠恢复哪些行历史上是小写，因此不做反向大小写回滚。
    pass
