# alembic/versions/20251109_resalloc_partial_unique.py
"""reservation_allocations: replace 5-col UNIQUE with two partial unique indexes

Why:
- PostgreSQL UNIQUE doesn't deduplicate NULLs. We need true uniqueness for both:
  1) batch_id IS NULL  -> unique(reservation_id, item_id, warehouse_id, location_id)
  2) batch_id IS NOT NULL -> unique(reservation_id, item_id, warehouse_id, location_id, batch_id)
- This aligns with app-side UPSERT:
  - ON CONFLICT (res_id,item_id,wh_id,loc_id) when batch_id IS NULL
  - ON CONFLICT (res_id,item_id,wh_id,loc_id,batch_id) when batch_id IS NOT NULL
"""

from alembic import op

revision = "20251109_resalloc_partial_unique"
down_revision = "20251108_reservation_allocations"  # 保持不变
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        -- 1) 旧的5列唯一是“约束”，不是裸索引；必须按约束删除
        ALTER TABLE reservation_allocations
          DROP CONSTRAINT IF EXISTS uq_resalloc_res_item_wh_loc_batch;

        -- 保险：若历史上被创建成裸索引，顺手再删一次索引（不存在则忽略）
        DROP INDEX IF EXISTS uq_resalloc_res_item_wh_loc_batch;

        -- 2) 创建两条 partial unique（NULL/NOT NULL 各自唯一）
        CREATE UNIQUE INDEX IF NOT EXISTS uq_resalloc_null_batch
          ON reservation_allocations (reservation_id, item_id, warehouse_id, location_id)
          WHERE batch_id IS NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_resalloc_with_batch
          ON reservation_allocations (reservation_id, item_id, warehouse_id, location_id, batch_id)
          WHERE batch_id IS NOT NULL;

        -- 3) 常用查询索引（若已存在不会重复创建）
        CREATE INDEX IF NOT EXISTS ix_resalloc_reservation
          ON reservation_allocations (reservation_id);
        CREATE INDEX IF NOT EXISTS ix_resalloc_item_wh_loc
          ON reservation_allocations (item_id, warehouse_id, location_id);
        CREATE INDEX IF NOT EXISTS ix_resalloc_batch
          ON reservation_allocations (batch_id);
        """
    )


def downgrade():
    op.execute(
        """
        -- 回滚：删除 partial unique，恢复5列唯一“约束”
        DROP INDEX IF EXISTS ix_resalloc_batch;
        DROP INDEX IF EXISTS ix_resalloc_item_wh_loc;
        DROP INDEX IF EXISTS ix_resalloc_reservation;

        DROP INDEX IF EXISTS uq_resalloc_with_batch;
        DROP INDEX IF EXISTS uq_resalloc_null_batch;

        ALTER TABLE reservation_allocations
          ADD CONSTRAINT uq_resalloc_res_item_wh_loc_batch
          UNIQUE (reservation_id, item_id, warehouse_id, location_id, batch_id);
        """
    )
