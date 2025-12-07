"""Remove legacy columns from stocks: qty_on_hand, batch_id
Rebuild dependent views v_onhand / v_returns_pool
"""

from alembic import op
import sqlalchemy as sa


revision = "clean_stocks_legacy_fields"
down_revision = "batch_supplier_lot_varchar"
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Drop dependent views
    op.execute("DROP VIEW IF EXISTS v_onhand;")
    op.execute("DROP VIEW IF EXISTS v_returns_pool;")

    # Step 2: Remove legacy columns from stocks
    with op.batch_alter_table("stocks") as batch:
        # qty_on_hand 是遗留字段（应由 column_property 替代）
        batch.drop_column("qty_on_hand")
        # batch_id 也是遗留字段，与 batch_code 模型冲突
        batch.drop_column("batch_id")

    # Step 3: Recreate views using correct fields
    # v_onhand: aggregates qty from stocks
    op.execute(
        """
        CREATE VIEW v_onhand AS
        SELECT
            warehouse_id,
            item_id,
            batch_code,
            qty AS qty_on_hand
        FROM stocks;
        """
    )

    # v_returns_pool: same logic, but used for returns workflow
    op.execute(
        """
        CREATE VIEW v_returns_pool AS
        SELECT
            warehouse_id,
            item_id,
            batch_code,
            qty AS qty_on_hand
        FROM stocks
        WHERE qty > 0;
        """
    )


def downgrade():
    # Step 1: Drop reconstructed views
    op.execute("DROP VIEW IF EXISTS v_onhand;")
    op.execute("DROP VIEW IF EXISTS v_returns_pool;")

    # Step 2: Restore legacy columns
    with op.batch_alter_table("stocks") as batch:
        batch.add_column(sa.Column("qty_on_hand", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))

    # Step 3: Restore original views (legacy behavior)
    op.execute(
        """
        CREATE VIEW v_onhand AS
        SELECT
            warehouse_id,
            item_id,
            batch_code,
            qty_on_hand
        FROM stocks;
        """
    )

    op.execute(
        """
        CREATE VIEW v_returns_pool AS
        SELECT
            warehouse_id,
            item_id,
            batch_code,
            qty_on_hand
        FROM stocks
        WHERE qty_on_hand > 0;
        """
    )
