"""add receive tasks tables

Revision ID: a198e23eef2d
Revises: aec78fc440a2
Create Date: 2025-11-29 17:26:18.880010
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a198e23eef2d'
down_revision: Union[str, Sequence[str], None] = 'aec78fc440a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create receive_tasks & receive_task_lines"""
    op.create_table(
        'receive_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('po_id', sa.Integer(), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('supplier_name', sa.String(length=255), nullable=True),
        sa.Column('warehouse_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column('remark', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('ix_receive_tasks_po_id', 'receive_tasks', ['po_id'])
    op.create_index('ix_receive_tasks_supplier_id', 'receive_tasks', ['supplier_id'])
    op.create_index('ix_receive_tasks_warehouse_id', 'receive_tasks', ['warehouse_id'])

    op.create_table(
        'receive_task_lines',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('receive_tasks.id', ondelete="CASCADE"), nullable=False),
        sa.Column('po_line_id', sa.Integer(), nullable=True),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('item_name', sa.String(length=255), nullable=True),
        sa.Column('batch_code', sa.String(length=64), nullable=True),
        sa.Column('expected_qty', sa.Integer(), nullable=True),
        sa.Column('scanned_qty', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('committed_qty', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column('remark', sa.String(length=255), nullable=True),
    )

    op.create_index('ix_receive_task_lines_task_id', 'receive_task_lines', ['task_id'])
    op.create_index('ix_receive_task_lines_po_line_id', 'receive_task_lines', ['po_line_id'])
    op.create_index('ix_receive_task_lines_item_id', 'receive_task_lines', ['item_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_receive_task_lines_item_id', table_name='receive_task_lines')
    op.drop_index('ix_receive_task_lines_po_line_id', table_name='receive_task_lines')
    op.drop_index('ix_receive_task_lines_task_id', table_name='receive_task_lines')
    op.drop_table('receive_task_lines')

    op.drop_index('ix_receive_tasks_warehouse_id', table_name='receive_tasks')
    op.drop_index('ix_receive_tasks_supplier_id', table_name='receive_tasks')
    op.drop_index('ix_receive_tasks_po_id', table_name='receive_tasks')
    op.drop_table('receive_tasks')
