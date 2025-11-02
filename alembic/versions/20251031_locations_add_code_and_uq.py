"""locations: add `code` column + unique (warehouse_id, code)

Revision ID: 20251031_locations_add_code_and_uq
Revises: 20251031_item_barcodes_and_shelf_life
Create Date: 2025-10-31

目的
- 为 locations 补齐机器可读的库位编码 `code`（LOC 规范字段）
- 用现有 `name` 原样回填 `code`，保持行为不变
- 将 `code` 设为 NOT NULL，并在 (warehouse_id, code) 上加唯一约束
- 不移除 (warehouse_id, name) 的历史唯一约束，确保兼容（如需可在后续迁移中移除）

注
- 本迁移只做结构与数据回填，不改任何外键；引用仍以 id 为准
"""

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision = "20251031_locations_add_code_and_uq"
down_revision = "20251031_item_barcodes_and_shelf_life"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 增加 code 列（允许为空，便于回填）
    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code", sa.Text(), nullable=True))

    # 2) 用历史 name 回填 code（保持一一对应）
    op.execute("UPDATE locations SET code = name WHERE code IS NULL")

    # 3) 将 code 设为 NOT NULL
    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.alter_column("code", existing_type=sa.Text(), nullable=False)

    # 4) 在 (warehouse_id, code) 上建立唯一约束（若已存在则跳过）
    #    使用 DDL 容错，避免重复执行时报错
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_locations_wh_code'
          ) THEN
            ALTER TABLE locations
              ADD CONSTRAINT uq_locations_wh_code UNIQUE (warehouse_id, code);
          END IF;
        END $$;
        """
    )

    # 5) 可选：为常用查询增加索引（非唯一）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n
              ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_locations_wh_code' AND n.nspname = 'public'
          ) THEN
            CREATE INDEX ix_locations_wh_code ON locations (warehouse_id, code);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # 逆向：删除索引与唯一约束，再移除列
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n
              ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_locations_wh_code' AND n.nspname = 'public'
          ) THEN
            DROP INDEX ix_locations_wh_code;
          END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_locations_wh_code'
          ) THEN
            ALTER TABLE locations
              DROP CONSTRAINT uq_locations_wh_code;
          END IF;
        END $$;
        """
    )

    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.drop_column("code")
