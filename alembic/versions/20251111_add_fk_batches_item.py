"""add FK: batches.item_id -> items(id)

Revision ID: 20251111_add_fk_batches_item
Revises: 20251111_v2_core_drop_ledger_loc_and_create_snapshots
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# identifiers
revision = "20251111_add_fk_batches_item"
down_revision = "20251111_v2_core_drop_ledger_loc_and_create_snapshots"
branch_labels = None
depends_on = None


def _fk_exists(conn, table: str, name: str, schema: str = "public") -> bool:
    insp = Inspector.from_engine(conn)
    return any(fk.get("name") == name for fk in insp.get_foreign_keys(table, schema=schema))


def upgrade():
    conn = op.get_bind()
    # 幂等：已存在则跳过
    if not _fk_exists(conn, table="batches", name="fk_batches_item", schema="public"):
        op.create_foreign_key(
            constraint_name="fk_batches_item",
            source_table="batches",
            referent_table="items",
            local_cols=["item_id"],
            remote_cols=["id"],
            source_schema="public",
            referent_schema="public",
            ondelete=None,
        )


def downgrade():
    conn = op.get_bind()
    if _fk_exists(conn, table="batches", name="fk_batches_item", schema="public"):
        op.drop_constraint("fk_batches_item", "batches", type_="foreignkey", schema="public")
