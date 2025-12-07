"""reservation_allocations strong-consistency table

Revision ID: 20251108_reservation_allocations
Revises: 6ecb881a0e74
Create Date: 2025-11-08 10:42:18.851686
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251108_reservation_allocations"
down_revision: Union[str, Sequence[str], None] = "6ecb881a0e74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reservation_allocations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("reservation_id", sa.BigInteger, nullable=False),
        sa.Column("item_id", sa.BigInteger, nullable=False),
        sa.Column("warehouse_id", sa.BigInteger, nullable=False),
        sa.Column("location_id", sa.BigInteger, nullable=False),
        sa.Column("batch_id", sa.BigInteger, nullable=True),
        sa.Column("qty", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("qty > 0", name="ck_resalloc_qty_positive"),
    )

    # FKs（与你现有的表名对应）
    op.create_foreign_key(
        "fk_resalloc_reservation",
        "reservation_allocations",
        "reservations",
        ["reservation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_resalloc_batch",
        "reservation_allocations",
        "batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 幂等聚合粒度（同一次 reservation 内，同一来源唯一）
    op.create_unique_constraint(
        "uq_resalloc_res_item_wh_loc_batch",
        "reservation_allocations",
        ["reservation_id", "item_id", "warehouse_id", "location_id", "batch_id"],
    )

    # 常用索引
    op.create_index("ix_resalloc_reservation", "reservation_allocations", ["reservation_id"])
    op.create_index(
        "ix_resalloc_item_wh_loc",
        "reservation_allocations",
        ["item_id", "warehouse_id", "location_id"],
    )
    op.create_index("ix_resalloc_batch", "reservation_allocations", ["batch_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_resalloc_batch", table_name="reservation_allocations")
    op.drop_index("ix_resalloc_item_wh_loc", table_name="reservation_allocations")
    op.drop_index("ix_resalloc_reservation", table_name="reservation_allocations")
    op.drop_constraint(
        "uq_resalloc_res_item_wh_loc_batch", "reservation_allocations", type_="unique"
    )
    op.drop_constraint("fk_resalloc_batch", "reservation_allocations", type_="foreignkey")
    op.drop_constraint("fk_resalloc_reservation", "reservation_allocations", type_="foreignkey")
    op.drop_table("reservation_allocations")
