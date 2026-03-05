"""scope phase3: pick_tasks/outbound_commits_v2 add scope + uq include scope

Revision ID: de0ea3cf52ec
Revises: 1ff62e046f8e
Create Date: 2026-02-13 15:08:59.899944

Phase 3 第二刀（作业与出库证据进入双宇宙）：

- pick_tasks 增加 scope（biz_scope）
- uq_pick_tasks_ref_wh 从 UNIQUE(ref, warehouse_id) 升级为 UNIQUE(scope, ref, warehouse_id)
- outbound_commits_v2 增加 scope（biz_scope）
- uq_outbound_commits_v2_platform_shop_ref 从 UNIQUE(platform, shop_id, ref) 升级为 UNIQUE(scope, platform, shop_id, ref)
- 补充常用辅助索引
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "de0ea3cf52ec"
down_revision: Union[str, Sequence[str], None] = "1ff62e046f8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- small helpers ----------
def _col_exists(conn, table: str, col: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, col),
    ).first()
    return res is not None


def _constraint_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        "SELECT 1 FROM pg_constraint WHERE conname=%s LIMIT 1",
        (name,),
    ).first()
    return res is not None


def _index_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='i' AND c.relname=%s AND n.nspname='public'
        LIMIT 1
        """,
        (name,),
    ).first()
    return res is not None


# ---------------- upgrade ----------------
def upgrade() -> None:
    conn = op.get_bind()

    # ---------------- pick_tasks ----------------
    if not _col_exists(conn, "pick_tasks", "scope"):
        op.execute("ALTER TABLE pick_tasks ADD COLUMN scope biz_scope")
        op.execute("ALTER TABLE pick_tasks ALTER COLUMN scope SET DEFAULT 'PROD'")

    op.execute("UPDATE pick_tasks SET scope='PROD' WHERE scope IS NULL")
    op.execute("ALTER TABLE pick_tasks ALTER COLUMN scope SET NOT NULL")
    op.execute("ALTER TABLE pick_tasks ALTER COLUMN scope DROP DEFAULT")

    # uq_pick_tasks_ref_wh：这是 UNIQUE INDEX（不是 constraint）
    if _index_exists(conn, "uq_pick_tasks_ref_wh"):
        op.execute("DROP INDEX IF EXISTS uq_pick_tasks_ref_wh")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pick_tasks_ref_wh
          ON pick_tasks(scope, ref, warehouse_id)
        """
    )

    if not _index_exists(conn, "ix_pick_tasks_scope_status"):
        op.execute("CREATE INDEX ix_pick_tasks_scope_status ON pick_tasks(scope, status)")

    # ---------------- outbound_commits_v2 ----------------
    if not _col_exists(conn, "outbound_commits_v2", "scope"):
        op.execute("ALTER TABLE outbound_commits_v2 ADD COLUMN scope biz_scope")
        op.execute("ALTER TABLE outbound_commits_v2 ALTER COLUMN scope SET DEFAULT 'PROD'")

    op.execute("UPDATE outbound_commits_v2 SET scope='PROD' WHERE scope IS NULL")
    op.execute("ALTER TABLE outbound_commits_v2 ALTER COLUMN scope SET NOT NULL")
    op.execute("ALTER TABLE outbound_commits_v2 ALTER COLUMN scope DROP DEFAULT")

    # uq_outbound_commits_v2_platform_shop_ref：这是 UNIQUE CONSTRAINT
    if _constraint_exists(conn, "uq_outbound_commits_v2_platform_shop_ref"):
        op.execute(
            "ALTER TABLE outbound_commits_v2 "
            "DROP CONSTRAINT IF EXISTS uq_outbound_commits_v2_platform_shop_ref"
        )

    op.execute(
        """
        ALTER TABLE outbound_commits_v2
        ADD CONSTRAINT uq_outbound_commits_v2_platform_shop_ref
        UNIQUE (scope, platform, shop_id, ref)
        """
    )

    if not _index_exists(conn, "ix_outbound_commits_v2_scope_trace_id"):
        op.execute("CREATE INDEX ix_outbound_commits_v2_scope_trace_id ON outbound_commits_v2(scope, trace_id)")


# ---------------- downgrade ----------------
def downgrade() -> None:
    conn = op.get_bind()

    # outbound_commits_v2
    if _index_exists(conn, "ix_outbound_commits_v2_scope_trace_id"):
        op.execute("DROP INDEX IF EXISTS ix_outbound_commits_v2_scope_trace_id")

    if _constraint_exists(conn, "uq_outbound_commits_v2_platform_shop_ref"):
        op.execute(
            "ALTER TABLE outbound_commits_v2 "
            "DROP CONSTRAINT IF EXISTS uq_outbound_commits_v2_platform_shop_ref"
        )
    op.execute(
        """
        ALTER TABLE outbound_commits_v2
        ADD CONSTRAINT uq_outbound_commits_v2_platform_shop_ref
        UNIQUE (platform, shop_id, ref)
        """
    )

    if _col_exists(conn, "outbound_commits_v2", "scope"):
        op.execute("ALTER TABLE outbound_commits_v2 DROP COLUMN scope")

    # pick_tasks
    if _index_exists(conn, "ix_pick_tasks_scope_status"):
        op.execute("DROP INDEX IF EXISTS ix_pick_tasks_scope_status")

    if _index_exists(conn, "uq_pick_tasks_ref_wh"):
        op.execute("DROP INDEX IF EXISTS uq_pick_tasks_ref_wh")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pick_tasks_ref_wh
          ON pick_tasks(ref, warehouse_id)
        """
    )

    if _col_exists(conn, "pick_tasks", "scope"):
        op.execute("ALTER TABLE pick_tasks DROP COLUMN scope")
