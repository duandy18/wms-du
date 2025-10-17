"""add outbound_commits (idempotency anchor)

Revision ID: 20251016_add_outbound_commits
Revises: 20251015_fill_item_id_on_ledger_insert
Create Date: 2025-10-16

说明：
- 建表 outbound_commits：记录幂等键与原始请求数量。
- UNIQUE(ref, item_id, location_id) 作为幂等锚点。
- 为 stock_ledger(ref) 补轻量索引（若不存在），便于回放与审计。
"""

from alembic import op

# --- 迁移标识 ---
revision = "20251016_add_outbound_commits"
down_revision = "20251015_fill_item_id_on_ledger_insert"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 建表（IF NOT EXISTS）
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_commits (
            id SERIAL PRIMARY KEY,
            ref VARCHAR(64) NOT NULL,
            item_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # 2) 唯一索引（幂等锚点）
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_outbound_ref_item_loc
        ON outbound_commits(ref, item_id, location_id);
        """
    )

    # 3) 辅助索引（审计/回放）
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_outbound_commits_ref
        ON outbound_commits(ref);
        """
    )

    # 4) ledger(ref) 索引（如缺则补）
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stock_ledger_ref
        ON stock_ledger(ref);
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_ref;")
    op.execute("DROP INDEX IF EXISTS ix_outbound_commits_ref;")
    op.execute("DROP INDEX IF EXISTS uq_outbound_ref_item_loc;")
    op.execute("DROP TABLE IF EXISTS outbound_commits;")
