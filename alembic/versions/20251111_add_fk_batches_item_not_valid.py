"""v2: add FK batches.item_id -> items(id) (NOT VALID first, then VALIDATE)

Revision ID: 20251111_add_fk_batches_item_not_valid
Revises: 20251111_v2_core_drop_ledger_loc_and_create_snapshots
Create Date: 2025-11-11
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "20251111_add_fk_batches_item_not_valid"
down_revision = "20251111_v2_core_drop_ledger_loc_and_create_snapshots"
branch_labels = None
depends_on = None


def _fk_exists(conn, table: str, name: str, schema: str = "public") -> bool:
    insp = Inspector.from_engine(conn)
    return any(fk.get("name") == name for fk in insp.get_foreign_keys(table, schema=schema))


def upgrade():
    conn = op.get_bind()

    # 1) 先用 NOT VALID 创建（若不存在）
    if not _fk_exists(conn, table="batches", name="fk_batches_item", schema="public"):
        op.execute("""
            ALTER TABLE public.batches
            ADD CONSTRAINT fk_batches_item
            FOREIGN KEY (item_id) REFERENCES public.items(id) NOT VALID
        """)

    # 2) 尝试验证（若有孤儿会报错；保持幂等）
    try:
        op.execute("ALTER TABLE public.batches VALIDATE CONSTRAINT fk_batches_item")
    except Exception:
        # 留存为 NOT VALID，后续清孤儿再 validate
        pass


def downgrade():
    conn = op.get_bind()
    if _fk_exists(conn, table="batches", name="fk_batches_item", schema="public"):
        op.execute("ALTER TABLE public.batches DROP CONSTRAINT fk_batches_item")
