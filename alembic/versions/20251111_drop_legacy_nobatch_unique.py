"""清理：删除 stocks 上 legacy 的 (item_id, location_id) WHERE batch_id IS NULL 条件唯一"""

from alembic import op
import sqlalchemy as sa

revision = "20251111_drop_legacy_nobatch_unique"
down_revision = "20251111_post_cleanup_legacy_location_refs"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # 在 pg_constraint 中查找 stocks 的 partial unique，且定义里包含 batch_id IS NULL
    conn.execute(sa.text("""
    DO $$
    DECLARE
      r record;
    BEGIN
      FOR r IN
        SELECT conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'stocks'
          AND c.contype = 'u'
          AND pg_get_constraintdef(c.oid) ILIKE '%WHERE%batch_id IS NULL%'
      LOOP
        EXECUTE format('ALTER TABLE stocks DROP CONSTRAINT %I', r.conname);
      END LOOP;
    END$$;
    """))


def downgrade():
    # 不恢复 legacy 条件唯一（不可逆清理）
    pass
