"""po_plan_status_purify_and_close_cancel_fields

Revision ID: 71f615ca4529
Revises: c256687896bc
Create Date: 2026-02-19 11:01:56.453146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "71f615ca4529"
down_revision: Union[str, Sequence[str], None] = "c256687896bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 新增：关闭/取消审计字段（计划层）
    op.add_column("purchase_orders", sa.Column("close_reason", sa.String(length=32), nullable=True))
    op.add_column("purchase_orders", sa.Column("close_note", sa.Text(), nullable=True))
    op.add_column("purchase_orders", sa.Column("closed_by", sa.BigInteger(), nullable=True))

    op.add_column("purchase_orders", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchase_orders", sa.Column("canceled_reason", sa.String(length=64), nullable=True))
    op.add_column("purchase_orders", sa.Column("canceled_by", sa.BigInteger(), nullable=True))

    # 2) 数据迁移：纯化 PO.status 语义（计划生命周期）
    # - RECEIVED（历史派生态）=> CLOSED + AUTO_COMPLETED
    # - PARTIAL（历史派生态）  => CREATED
    #
    # 若 RECEIVED 行 closed_at 为空，补 now()（避免“已关闭但无时间”）
    op.execute(
        """
        UPDATE purchase_orders
           SET status = 'CLOSED',
               close_reason = COALESCE(close_reason, 'AUTO_COMPLETED'),
               closed_at = COALESCE(closed_at, now())
         WHERE status = 'RECEIVED'
        """
    )
    op.execute(
        """
        UPDATE purchase_orders
           SET status = 'CREATED'
         WHERE status = 'PARTIAL'
        """
    )

    # 3) 合同护栏：status 只允许计划生命周期值
    op.create_check_constraint(
        "ck_purchase_orders_status_plan",
        "purchase_orders",
        "status IN ('CREATED', 'CANCELED', 'CLOSED')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 逆向：先撤护栏
    op.drop_constraint("ck_purchase_orders_status_plan", "purchase_orders", type_="check")

    # 尝试回滚状态（best-effort）
    # - AUTO_COMPLETED 的 CLOSED 还原为 RECEIVED
    # - CREATED 无法区分是原 CREATED 还是由 PARTIAL 回来的，故不回滚
    op.execute(
        """
        UPDATE purchase_orders
           SET status = 'RECEIVED'
         WHERE status = 'CLOSED'
           AND close_reason = 'AUTO_COMPLETED'
        """
    )

    # 删除字段（与 upgrade 相反顺序）
    op.drop_column("purchase_orders", "canceled_by")
    op.drop_column("purchase_orders", "canceled_reason")
    op.drop_column("purchase_orders", "canceled_at")

    op.drop_column("purchase_orders", "closed_by")
    op.drop_column("purchase_orders", "close_note")
    op.drop_column("purchase_orders", "close_reason")
