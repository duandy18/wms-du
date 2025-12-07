"""add outbound_ship_ops idempotency table (idempotent)

Revision ID: b3c92cd33ad4
Revises: 20251106_fix_ledger_uc_not_deferrable
Create Date: 2025-11-07 11:32:56.825081
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b3c92cd33ad4"
down_revision: Union[str, Sequence[str], None] = "20251106_fix_ledger_uc_not_deferrable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) 若表不存在则创建
    if not insp.has_table("outbound_ship_ops"):
        op.create_table(
            "outbound_ship_ops",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("ref", sa.String(length=128), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("location_id", sa.Integer(), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # 2) 幂等唯一约束（若缺则补）
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_ship_idem_key'
              ) THEN
                ALTER TABLE outbound_ship_ops
                  ADD CONSTRAINT uq_ship_idem_key
                  UNIQUE (store_id, ref, item_id, location_id);
              END IF;
            END $$;
            """
        )
    )

    # 3) 索引（若缺则补）
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_ship_ops_ref ON outbound_ship_ops (ref)"))
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ship_ops_store_ref ON outbound_ship_ops (store_id, ref)"
        )
    )


def downgrade() -> None:
    # 逆向幂等：先删索引/约束，再删表（若存在）
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ship_ops_store_ref"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ship_ops_ref"))
    op.execute(
        sa.text(
            "ALTER TABLE IF EXISTS outbound_ship_ops DROP CONSTRAINT IF EXISTS uq_ship_idem_key"
        )
    )
    op.execute(sa.text("DROP TABLE IF EXISTS outbound_ship_ops"))
