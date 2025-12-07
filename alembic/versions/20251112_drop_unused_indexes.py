# alembic/versions/20251112_drop_unused_indexes.py
from alembic import op

revision = "20251112_drop_unused_indexes"
down_revision = "20251110_orders_drop_legacy"
branch_labels = None
depends_on = None


def upgrade():
    # event_error_log
    op.execute("DROP INDEX IF EXISTS ix_event_error_stage;")
    op.execute("DROP INDEX IF EXISTS ix_event_error_occurred;")
    op.execute("DROP INDEX IF EXISTS ix_event_error_log_meta_gin;")

    # orders
    op.execute("DROP INDEX IF EXISTS ix_orders_no_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_orders_order_type;")
    op.execute("DROP INDEX IF EXISTS ix_orders_status;")
    op.execute("DROP INDEX IF EXISTS ix_orders_type_status;")

    # outbound_commits
    op.execute("DROP INDEX IF EXISTS ix_outbound_commits_ref;")
    op.execute("DROP INDEX IF EXISTS ux_outbound_commits_4cols;")
    op.execute("DROP INDEX IF EXISTS uq_outbound_ref_item_loc;")

    # platform_events
    op.execute("DROP INDEX IF EXISTS ix_platform_events_platform_occurred;")

    # pick_tasks / pick_task_lines
    op.execute("DROP INDEX IF EXISTS ix_pick_tasks_assigned;")
    op.execute("DROP INDEX IF EXISTS ix_pick_tasks_status;")
    op.execute("DROP INDEX IF EXISTS ix_pick_tasks_wh_prio;")
    op.execute("DROP INDEX IF EXISTS ix_pick_task_lines_item;")
    op.execute("DROP INDEX IF EXISTS ix_pick_task_lines_status;")
    op.execute("DROP INDEX IF EXISTS ix_pick_task_lines_task;")

    # reservation_lines / reservations
    op.execute("DROP INDEX IF EXISTS ix_reservation_lines_reservation_id;")
    op.execute("DROP INDEX IF EXISTS ix_reservations_batch_id;")
    op.execute("DROP INDEX IF EXISTS ix_reservations_order_id;")
    op.execute("DROP INDEX IF EXISTS ix_reservations_ref;")
    op.execute("DROP INDEX IF EXISTS ix_reservations_shop_ref;")

    # stock_ledger
    op.execute("DROP INDEX IF EXISTS ix_ledger_stock_ts;")
    op.execute("DROP INDEX IF EXISTS ix_ledger_wh_time;")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_stock_time;")

    # audit_events
    op.execute("DROP INDEX IF EXISTS ix_audit_events_outbound_ref_time;")


def downgrade():
    # 通常不重建；若需要回滚，这里可放最小索引定义
    pass
