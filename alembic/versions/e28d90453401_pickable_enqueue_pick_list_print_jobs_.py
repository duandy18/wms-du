"""pickable enqueue pick_list print_jobs and pick_task idempotency

Revision ID: e28d90453401
Revises: db4c943ff156
Create Date: 2026-02-02 15:10:35.035460
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e28d90453401"
down_revision: Union[str, Sequence[str], None] = "db4c943ff156"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 历史数据迁移：彻底清掉 RESERVED 字面残影
    op.execute(
        sa.text(
            """
            UPDATE orders
               SET status = 'PICKABLE',
                   updated_at = now()
             WHERE status = 'RESERVED'
            """
        )
    )

    # 1) print_jobs：待打印队列 + payload 快照（可回放、可审计）
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_type", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 幂等：同一个 ref 只允许一个 pick_list job
    op.create_index(
        "uq_print_jobs_pick_list_ref",
        "print_jobs",
        ["kind", "ref_type", "ref_id"],
        unique=True,
    )
    op.create_index("ix_print_jobs_status", "print_jobs", ["status"])
    op.create_index("ix_print_jobs_kind", "print_jobs", ["kind"])

    # 2) pick_tasks 幂等：用 (ref, warehouse_id) 唯一化
    #
    # 防御性清洗：测试库/历史数据可能存在重复 (ref, warehouse_id)（例如 T-DEMO）
    # 若不清洗，unique index 会在 upgrade-dev-test-db 阶段爆炸。
    # 规则：每组仅保留 id 最大的一条，其余删除（pick_task_lines ON DELETE CASCADE）。
    op.execute(
        sa.text(
            """
            WITH ranked AS (
              SELECT
                id,
                row_number() OVER (
                  PARTITION BY ref, warehouse_id
                  ORDER BY id DESC
                ) AS rn
              FROM pick_tasks
              WHERE ref IS NOT NULL AND ref <> ''
            )
            DELETE FROM pick_tasks p
            USING ranked r
            WHERE p.id = r.id
              AND r.rn > 1;
            """
        )
    )

    op.create_index(
        "uq_pick_tasks_ref_wh",
        "pick_tasks",
        ["ref", "warehouse_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_pick_tasks_ref_wh", table_name="pick_tasks")

    op.drop_index("ix_print_jobs_kind", table_name="print_jobs")
    op.drop_index("ix_print_jobs_status", table_name="print_jobs")
    op.drop_index("uq_print_jobs_pick_list_ref", table_name="print_jobs")
    op.drop_table("print_jobs")

    # downgrade 不反向改回 RESERVED（我们就是要彻底清掉预占概念）
