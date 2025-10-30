"""reservations + v_available view

Revision ID: 20251030_add_reservations_and_v_available
Revises: bf539dde5f39
Create Date: 2025-10-30 10:20:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251030_add_reservations_and_v_available"
down_revision = "bf539dde5f39"
branch_labels = None
depends_on = None


def upgrade():
    # 1) reservations 表（幂等）
    op.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
      id BIGSERIAL PRIMARY KEY,
      item_id INT NOT NULL,
      location_id INT NOT NULL,
      qty INT NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      ref TEXT NOT NULL,
      created_at TIMESTAMP NOT NULL DEFAULT now()
    );
    """)

    # 2) 唯一索引（幂等）——注意：这是“唯一索引”，不是“唯一约束”
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_reserve_idem
      ON reservations(ref, item_id, location_id)
      WHERE status='ACTIVE';
    """)

    # 3) 常用索引（幂等）
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_reservations_active_i_l
      ON reservations (item_id, location_id)
      WHERE status='ACTIVE';
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_stocks_i_l
      ON stocks (item_id, location_id);
    """)

    # 4) 只读视图（幂等替换）
    op.execute("""
    CREATE OR REPLACE VIEW v_available AS
    WITH s AS (
      SELECT item_id, location_id, SUM(qty) AS on_hand
      FROM stocks
      GROUP BY 1,2
    ),
    r AS (
      SELECT item_id, location_id, SUM(qty) AS reserved
      FROM reservations
      WHERE status='ACTIVE'
      GROUP BY 1,2
    )
    SELECT
      COALESCE(s.item_id, r.item_id) AS item_id,
      COALESCE(s.location_id, r.location_id) AS location_id,
      COALESCE(s.on_hand, 0) AS on_hand,
      COALESCE(r.reserved, 0) AS reserved,
      COALESCE(s.on_hand, 0) - COALESCE(r.reserved, 0) AS available
    FROM s
    FULL JOIN r USING (item_id, location_id);
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS v_available;")
    op.execute("DROP INDEX IF EXISTS idx_reservations_active_i_l;")
    op.execute("DROP INDEX IF EXISTS uq_reserve_idem;")
    op.execute("DROP TABLE IF EXISTS reservations;")
