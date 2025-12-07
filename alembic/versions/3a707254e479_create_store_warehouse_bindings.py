"""create store_warehouse bindings

Revision ID: 3a707254e479
Revises: e547920d161f
Create Date: 2025-11-07 16:38:13.475941
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "3a707254e479"
down_revision: Union[str, Sequence[str], None] = "e547920d161f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UQ = "uq_store_wh_unique"
_IDX = "ix_store_wh_store_default"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) 建表（若不存在）
    if not insp.has_table("store_warehouse", schema="public"):
        op.create_table(
            "store_warehouse",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "store_id",
                sa.BigInteger(),
                sa.ForeignKey("stores.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "warehouse_id",
                sa.BigInteger(),
                sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # 2) 唯一约束：同一店不可重复绑同一仓
    bind.execute(
        sa.text(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname='{_UQ}' AND conrelid=('public.store_warehouse')::regclass
          ) THEN
            ALTER TABLE store_warehouse
            ADD CONSTRAINT {_UQ} UNIQUE (store_id, warehouse_id);
          END IF;
        END $$;
    """)
    )

    # 3) 常用索引：按默认与优先级选仓
    bind.execute(
        sa.text(f"""
        CREATE INDEX IF NOT EXISTS {_IDX}
        ON store_warehouse (store_id, is_default, priority)
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(f"DROP INDEX IF EXISTS {_IDX}"))
    bind.execute(sa.text(f"ALTER TABLE IF EXISTS store_warehouse DROP CONSTRAINT IF EXISTS {_UQ}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS store_warehouse"))
