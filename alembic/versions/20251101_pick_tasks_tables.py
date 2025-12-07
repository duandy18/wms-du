"""pick tasks: head/lines/reservation mapping (task-driven picking foundation)

Revision ID: 20251101_pick_tasks_tables
Revises: 29ee69c580ea
Create Date: 2025-11-01 23:58:00
"""

from alembic import op

revision = "20251101_pick_tasks_tables"
down_revision = "29ee69c580ea"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 任务头
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_tasks (
          id            BIGSERIAL PRIMARY KEY,
          ref           TEXT UNIQUE,
          warehouse_id  BIGINT NOT NULL,
          source        TEXT NOT NULL DEFAULT 'SYSTEM',
          priority      INT  NOT NULL DEFAULT 100,
          status        TEXT NOT NULL DEFAULT 'READY',
          assigned_to   TEXT,
          note          TEXT,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_tasks_status ON pick_tasks(status);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pick_tasks_wh_prio ON pick_tasks(warehouse_id, priority);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_tasks_assigned ON pick_tasks(assigned_to)")

    # 2) 任务行
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_task_lines (
          id                 BIGSERIAL PRIMARY KEY,
          task_id            BIGINT NOT NULL REFERENCES pick_tasks(id) ON DELETE CASCADE,
          order_id           BIGINT,
          order_line_id      BIGINT,
          item_id            BIGINT NOT NULL,
          req_qty            BIGINT NOT NULL CHECK (req_qty > 0),
          picked_qty         BIGINT NOT NULL DEFAULT 0 CHECK (picked_qty >= 0),
          status             TEXT NOT NULL DEFAULT 'OPEN',
          prefer_pickface    BOOLEAN NOT NULL DEFAULT TRUE,
          target_location_id BIGINT,
          note               TEXT,
          created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (picked_qty <= req_qty)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_task_lines_task ON pick_task_lines(task_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_task_lines_item ON pick_task_lines(item_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pick_task_lines_status ON pick_task_lines(status);")

    # 3) 任务行 ⇄ 预留映射
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_task_line_reservations (
          id              BIGSERIAL PRIMARY KEY,
          task_line_id    BIGINT NOT NULL REFERENCES pick_task_lines(id) ON DELETE CASCADE,
          reservation_id  BIGINT NOT NULL,
          qty             BIGINT NOT NULL CHECK (qty > 0),
          UNIQUE (task_line_id, reservation_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ptlr_task_line ON pick_task_line_reservations(task_line_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ptlr_reservation ON pick_task_line_reservations(reservation_id);"
    )

    # 4) 状态枚举约束
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_pick_tasks_status') THEN
        ALTER TABLE pick_tasks
        ADD CONSTRAINT ck_pick_tasks_status
        CHECK (status IN ('READY','ASSIGNED','PICKING','DONE','CANCELLED'));
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_pick_task_lines_status') THEN
        ALTER TABLE pick_task_lines
        ADD CONSTRAINT ck_pick_task_lines_status
        CHECK (status IN ('OPEN','PARTIAL','DONE','CANCELLED'));
      END IF;
    END$$;
    """)

    # 5) 行状态自动机
    op.execute("""
    CREATE OR REPLACE FUNCTION pick_task_lines_auto_status()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.picked_qty <= 0 THEN
        NEW.status := 'OPEN';
      ELSIF NEW.picked_qty < NEW.req_qty THEN
        NEW.status := 'PARTIAL';
      ELSE
        NEW.status := 'DONE';
      END IF;
      NEW.updated_at := now();
      RETURN NEW;
    END$$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_ptl_autostatus') THEN
        CREATE TRIGGER trg_ptl_autostatus
        BEFORE INSERT OR UPDATE OF picked_qty, req_qty ON pick_task_lines
        FOR EACH ROW EXECUTE FUNCTION pick_task_lines_auto_status();
      END IF;
    END$$;
    """)

    # 6) 头状态聚合
    op.execute("""
    CREATE OR REPLACE FUNCTION pick_tasks_aggregate_status()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE
      remain INT;
    BEGIN
      SELECT COUNT(*) INTO remain
      FROM pick_task_lines
      WHERE task_id = NEW.task_id
        AND status NOT IN ('DONE','CANCELLED');
      IF remain = 0 THEN
        UPDATE pick_tasks SET status='DONE', updated_at=now()
        WHERE id = NEW.task_id AND status <> 'DONE';
      ELSE
        UPDATE pick_tasks SET updated_at=now()
        WHERE id = NEW.task_id;
      END IF;
      RETURN NULL;
    END$$;
    """)

    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_pt_aggregate') THEN
        CREATE TRIGGER trg_pt_aggregate
        AFTER INSERT OR UPDATE OF status, picked_qty, req_qty ON pick_task_lines
        FOR EACH ROW EXECUTE FUNCTION pick_tasks_aggregate_status();
      END IF;
    END$$;
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_pt_aggregate ON pick_task_lines;")
    op.execute("DROP FUNCTION IF EXISTS pick_tasks_aggregate_status;")
    op.execute("DROP TRIGGER IF EXISTS trg_ptl_autostatus ON pick_task_lines;")
    op.execute("DROP FUNCTION IF EXISTS pick_task_lines_auto_status;")
    op.execute("DROP TABLE IF EXISTS pick_task_line_reservations;")
    op.execute("DROP TABLE IF EXISTS pick_task_lines;")
    op.execute("DROP TABLE IF EXISTS pick_tasks;")
