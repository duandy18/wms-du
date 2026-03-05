"""drop_receive_task_and_draft_tables_phase4_final

Revision ID: 5621e0cd65e6
Revises: 6ee179e0cf29
Create Date: 2026-02-17 21:58:00.890606

Phase4 终态收敛：
- 删除 receive_task 执行层
- 删除 inbound_receipt_drafts 草稿层
- 收货统一收敛到 inbound_receipts(status=DRAFT/CONFIRMED)

⚠️ 本迁移不可逆（Irreversible）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5621e0cd65e6"
down_revision: Union[str, Sequence[str], None] = "6ee179e0cf29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    删除过渡模型与旧执行层。

    删除顺序必须：
    1) 子表
    2) 主表
    """

    # --- Draft 扫码证据 ---
    op.execute("DROP TABLE IF EXISTS inbound_receipt_draft_line_scan_events CASCADE")

    # --- Draft 行 ---
    op.execute("DROP TABLE IF EXISTS inbound_receipt_draft_lines CASCADE")

    # --- Draft 主表 ---
    op.execute("DROP TABLE IF EXISTS inbound_receipt_drafts CASCADE")

    # --- ReceiveTask 子表 ---
    op.execute("DROP TABLE IF EXISTS receive_task_lines CASCADE")

    # --- ReceiveTask 主表 ---
    op.execute("DROP TABLE IF EXISTS receive_tasks CASCADE")


def downgrade() -> None:
    raise RuntimeError(
        "Irreversible migration: receive_task and draft tables were permanently dropped."
    )
