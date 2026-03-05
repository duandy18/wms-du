"""add receive_task_scan_events

Revision ID: b22f0c8703d4
Revises: 9e560853fed6
Create Date: 2026-02-17 17:17:47.149675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b22f0c8703d4"
down_revision: Union[str, Sequence[str], None] = "9e560853fed6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "receive_task_scan_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("task_line_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("raw_barcode", sa.Text(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "parsed",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 索引（用于“最近扫码条码代号”快速查询）
    op.create_index(
        "ix_receive_task_scan_events_task_id_created_at",
        "receive_task_scan_events",
        ["task_id", "created_at"],
    )
    op.create_index(
        "ix_receive_task_scan_events_task_line_id_created_at",
        "receive_task_scan_events",
        ["task_line_id", "created_at"],
    )
    op.create_index(
        "ix_receive_task_scan_events_item_id_created_at",
        "receive_task_scan_events",
        ["item_id", "created_at"],
    )

    # FK 约束（执行层合同）
    op.create_foreign_key(
        "fk_receive_task_scan_events_task_id",
        "receive_task_scan_events",
        "receive_tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_receive_task_scan_events_task_line_id",
        "receive_task_scan_events",
        "receive_task_lines",
        ["task_line_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_receive_task_scan_events_task_line_id",
        "receive_task_scan_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_receive_task_scan_events_task_id",
        "receive_task_scan_events",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_receive_task_scan_events_item_id_created_at",
        table_name="receive_task_scan_events",
    )
    op.drop_index(
        "ix_receive_task_scan_events_task_line_id_created_at",
        table_name="receive_task_scan_events",
    )
    op.drop_index(
        "ix_receive_task_scan_events_task_id_created_at",
        table_name="receive_task_scan_events",
    )

    op.drop_table("receive_task_scan_events")
