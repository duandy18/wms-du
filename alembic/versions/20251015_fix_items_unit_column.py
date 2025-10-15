"""ensure items.unit exists (rename uom -> unit or add column)"""

from alembic import op

revision = "20251015_fix_items_unit_column"
down_revision = "20251015_snapshots_as_of_default"  # 按你当前 head 填；如果不同，用 `alembic heads -v` 的结果替换
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          has_items      boolean;
          has_unit       boolean;
          has_uom        boolean;
        BEGIN
          has_items := to_regclass('public.items') IS NOT NULL;

          IF has_items THEN
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='items' AND column_name='unit'
            ) INTO has_unit;

            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='items' AND column_name='uom'
            ) INTO has_uom;

            IF NOT has_unit THEN
              IF has_uom THEN
                -- 兼容旧列名：uom -> unit
                ALTER TABLE public.items RENAME COLUMN uom TO unit;
              ELSE
                -- 无 unit / 无 uom：新增 unit
                ALTER TABLE public.items
                  ADD COLUMN unit VARCHAR(8) NOT NULL DEFAULT 'EA';
                -- 可选：去掉默认，保留 NOT NULL 约束，避免误用默认
                ALTER TABLE public.items
                  ALTER COLUMN unit DROP DEFAULT;
              END IF;
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    pass
