"""add FKs on batches (item/location/warehouse)

Revision ID: 20251028_batches_add_foreign_keys
Revises: 20251028_perf_indexes_fefo_ledger
Create Date: 2025-10-28 12:02:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20251028_batches_add_foreign_keys"
down_revision = "20251028_perf_indexes_fefo_ledger"
branch_labels = None
depends_on = None

FK_ITEM = "fk_batches_item"
FK_LOC = "fk_batches_location"
FK_WH = "fk_batches_wh"


def _fk_exists(conn, table, name):
    return bool(
        conn.execute(
            sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname=:t AND c.conname=:n AND c.contype='f' LIMIT 1
    """),
            {"t": table, "n": name},
        ).scalar()
    )


def upgrade():
    conn = op.get_bind()
    if not _fk_exists(conn, "batches", FK_ITEM):
        op.create_foreign_key(
            FK_ITEM,
            "batches",
            "items",
            ["item_id"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        )
    if not _fk_exists(conn, "batches", FK_LOC):
        op.create_foreign_key(
            FK_LOC,
            "batches",
            "locations",
            ["location_id"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        )
    if not _fk_exists(conn, "batches", FK_WH):
        op.create_foreign_key(
            FK_WH,
            "batches",
            "warehouses",
            ["warehouse_id"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        )


def downgrade():
    conn = op.get_bind()
    if _fk_exists(conn, "batches", FK_WH):
        op.drop_constraint(FK_WH, "batches", type_="foreignkey")
    if _fk_exists(conn, "batches", FK_LOC):
        op.drop_constraint(FK_LOC, "batches", type_="foreignkey")
    if _fk_exists(conn, "batches", FK_ITEM):
        op.drop_constraint(FK_ITEM, "batches", type_="foreignkey")
