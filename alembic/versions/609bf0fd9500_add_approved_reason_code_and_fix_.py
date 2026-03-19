"""add_approved_reason_code_and_fix_history_flow

Revision ID: 609bf0fd9500
Revises: ab9b7b00f8b1
Create Date: 2026-03-19 15:04:00.693006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "609bf0fd9500"
down_revision: Union[str, Sequence[str], None] = "ab9b7b00f8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) reconciliation 表增加 approved_reason_code（工作态字段，可空）
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("approved_reason_code", sa.String(length=32), nullable=True),
    )

    # 2) history 表增加 approved_reason_code（归档态字段，先可空，回填后再收紧）
    op.add_column(
        "shipping_bill_reconciliation_histories",
        sa.Column("approved_reason_code", sa.String(length=32), nullable=True),
    )

    # 3) 修正历史表旧错误状态值 accepted_bill_only -> approved_bill_only
    op.execute(
        """
        UPDATE shipping_bill_reconciliation_histories
        SET result_status = 'approved_bill_only'
        WHERE result_status = 'accepted_bill_only'
        """
    )

    # 4) 回填 history.approved_reason_code
    #    历史表是最终快照，直接以 result_status 作为 approved_reason_code
    op.execute(
        """
        UPDATE shipping_bill_reconciliation_histories
        SET approved_reason_code = result_status
        WHERE approved_reason_code IS NULL
        """
    )

    # 5) 回填 reconciliation.approved_reason_code
    #    只给“已审批但尚未清掉”的老数据补 code：
    #    - diff -> resolved
    #    - bill_only -> approved_bill_only
    op.execute(
        """
        UPDATE shipping_record_reconciliations
        SET approved_reason_code = CASE
            WHEN status = 'diff' THEN 'resolved'
            WHEN status = 'bill_only' THEN 'approved_bill_only'
            ELSE approved_reason_code
        END
        WHERE approved_at IS NOT NULL
          AND approved_reason_code IS NULL
        """
    )

    # 6) history 表 result_status 约束重建：统一为数据库真相
    op.drop_constraint(
        "ck_shipping_bill_reconciliation_histories_result_status",
        "shipping_bill_reconciliation_histories",
        type_="check",
    )
    op.create_check_constraint(
        "ck_shipping_bill_reconciliation_histories_result_status",
        "shipping_bill_reconciliation_histories",
        "result_status IN ('matched', 'approved_bill_only', 'resolved')",
    )

    # 7) reconciliation 表 approved_reason_code 约束
    op.create_check_constraint(
        "ck_shipping_record_reconciliations_approved_reason_code",
        "shipping_record_reconciliations",
        "approved_reason_code IS NULL OR approved_reason_code IN ('matched', 'approved_bill_only', 'resolved')",
    )

    # 8) reconciliation 表：只要 approved_at 非空，approved_reason_code 必须非空
    op.create_check_constraint(
        "ck_shipping_record_reconciliations_approved_requires_code",
        "shipping_record_reconciliations",
        "approved_at IS NULL OR approved_reason_code IS NOT NULL",
    )

    # 9) history 表 approved_reason_code 约束
    op.create_check_constraint(
        "ck_shipping_bill_reconciliation_histories_approved_reason_code",
        "shipping_bill_reconciliation_histories",
        "approved_reason_code IN ('matched', 'approved_bill_only', 'resolved')",
    )

    # 10) history 表 approved_reason_code 收紧为 NOT NULL
    op.alter_column(
        "shipping_bill_reconciliation_histories",
        "approved_reason_code",
        existing_type=sa.String(length=32),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.alter_column(
        "shipping_bill_reconciliation_histories",
        "approved_reason_code",
        existing_type=sa.String(length=32),
        nullable=True,
    )

    op.drop_constraint(
        "ck_shipping_bill_reconciliation_histories_approved_reason_code",
        "shipping_bill_reconciliation_histories",
        type_="check",
    )

    op.drop_constraint(
        "ck_shipping_record_reconciliations_approved_requires_code",
        "shipping_record_reconciliations",
        type_="check",
    )

    op.drop_constraint(
        "ck_shipping_record_reconciliations_approved_reason_code",
        "shipping_record_reconciliations",
        type_="check",
    )

    op.drop_constraint(
        "ck_shipping_bill_reconciliation_histories_result_status",
        "shipping_bill_reconciliation_histories",
        type_="check",
    )
    op.create_check_constraint(
        "ck_shipping_bill_reconciliation_histories_result_status",
        "shipping_bill_reconciliation_histories",
        "result_status IN ('matched', 'accepted_bill_only', 'resolved')",
    )

    op.drop_column("shipping_bill_reconciliation_histories", "approved_reason_code")
    op.drop_column("shipping_record_reconciliations", "approved_reason_code")
