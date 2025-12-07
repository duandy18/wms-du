from alembic import op

revision = "20251112_drop_unused_indexes_v2"
down_revision = "20251112_merge_after_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    for idx in [
        "ix_stocks_item",
        "ix_stocks_location",
        "ix_stock_ledger_location_id",
        "ix_audit_events_category",
        "ix_stock_snapshots_item_loc_ts",
        "ix_locations_wh_code",
        "idx_reservations_active_i_l",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx};")


def downgrade():
    # 无需恢复，所有索引均由新唯一约束/复合索引取代
    pass
