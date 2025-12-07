"""fix locations.id default -> nextval('locations_id_seq')

Revision ID: 3f_fix_locations_id_default_seq_binding
Revises: 2ec8ea5fe9f2
Create Date: 2025-11-10 15:45:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "3f_fix_locations_id_default_seq_binding"
down_revision = "2ec8ea5fe9f2"
branch_labels = None
depends_on = None


def upgrade():
    # 1️⃣ 修正列默认值（幂等）
    op.execute("""
    DO $$
    BEGIN
      IF (
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='locations'
          AND column_name='id'
      ) IS DISTINCT FROM 'nextval(''public.locations_id_seq''::regclass)' THEN
        ALTER TABLE public.locations
          ALTER COLUMN id SET DEFAULT nextval('public.locations_id_seq'::regclass);
      END IF;
    END$$;
    """)

    # 2️⃣ 绑定序列所有权（幂等）
    op.execute("""
    ALTER SEQUENCE IF EXISTS public.locations_id_seq
      OWNED BY public.locations.id;
    """)

    # 3️⃣ 自动检测并同步序列位置（防止 Duplicate Key）
    op.execute("""
    DO $$
    DECLARE
      maxid bigint;
      targetval bigint;
    BEGIN
      SELECT COALESCE(MAX(id), 0) INTO maxid FROM public.locations;

      -- 逻辑：
      --  若表为空，则设置 targetval = 1（下一次 nextval() = 1）
      --  若表已有数据，则设置 targetval = MAX(id) + 1（下一次 nextval() = maxid+1）
      IF maxid < 1 THEN
        targetval := 1;
      ELSE
        targetval := maxid + 1;
      END IF;

      -- 设定序列下次取值，不消耗 nextval()
      PERFORM setval('public.locations_id_seq', targetval, false);

      RAISE NOTICE 'locations_id_seq synchronized to % (table max id was %)', targetval, maxid;
    END$$;
    """)


def downgrade():
    # 回滚时移除默认值与所有权
    op.execute("""
    ALTER TABLE public.locations
      ALTER COLUMN id DROP DEFAULT;
    ALTER SEQUENCE IF EXISTS public.locations_id_seq OWNED BY NONE;
    """)
