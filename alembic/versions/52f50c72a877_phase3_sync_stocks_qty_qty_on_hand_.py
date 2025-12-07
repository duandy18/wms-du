"""phase3: sync stocks.qty <-> qty_on_hand during transition"""

from alembic import op
import sqlalchemy as sa

# 替换为你当前 head
revision = "20251111_sync_qty_columns"
down_revision = "20251111_add_stocks_qty_int"
branch_labels = None
depends_on = None


def upgrade():
    # 1) qty_on_hand 增加默认值 0，避免仅写 qty 时出现 NULL 违约
    op.execute(
        """
        ALTER TABLE stocks
          ALTER COLUMN qty_on_hand SET DEFAULT 0;
        """
    )

    # 2) 回填历史 NULL
    op.execute("UPDATE stocks SET qty_on_hand = 0 WHERE qty_on_hand IS NULL;")
    op.execute("UPDATE stocks SET qty = qty_on_hand WHERE qty IS NULL;")

    # 3) 安装触发器函数（保持两列一致）
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stocks_qty_sync() RETURNS trigger AS $$
        BEGIN
          -- 互补：谁为 NULL 就用另一列补上
          IF NEW.qty IS NULL AND NEW.qty_on_hand IS NOT NULL THEN
            NEW.qty := NEW.qty_on_hand;
          ELSIF NEW.qty_on_hand IS NULL AND NEW.qty IS NOT NULL THEN
            NEW.qty_on_hand := NEW.qty;
          END IF;

          -- 保证一致：若两者都不为空但不同，以 NEW.qty 为准镜像到 qty_on_hand
          -- （也可反过来，以业务决定；我们统一以 qty 为唯一事实源）
          IF NEW.qty IS NOT NULL THEN
            NEW.qty_on_hand := NEW.qty;
          END IF;

          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )

    # 4) 绑定触发器：INSERT、UPDATE 时同步
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stocks_qty_sync ON stocks;
        CREATE TRIGGER trg_stocks_qty_sync
          BEFORE INSERT OR UPDATE ON stocks
          FOR EACH ROW
          EXECUTE FUNCTION stocks_qty_sync();
        """
    )


def downgrade():
    # 移除触发器与函数
    op.execute("DROP TRIGGER IF EXISTS trg_stocks_qty_sync ON stocks;")
    op.execute("DROP FUNCTION IF EXISTS stocks_qty_sync();")

    # 撤销默认值
    op.execute("ALTER TABLE stocks ALTER COLUMN qty_on_hand DROP DEFAULT;")
