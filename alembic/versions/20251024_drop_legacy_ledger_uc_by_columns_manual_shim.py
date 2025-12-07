"""shim: restore missing 20251024_drop_legacy_ledger_uc_by_columns (no-op)"""

revision = "20251024_drop_legacy_ledger_uc_by_columns"
down_revision = "u9_order_state_snapshot"  # 目录里已存在的一条稳定链
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
