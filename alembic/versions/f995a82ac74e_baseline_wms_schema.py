"""baseline wms schema (safe-create if missing)

Revision ID: f995a82ac74e
Revises:
Create Date: 2025-10-06 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f995a82ac74e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ------------ helpers ------------
def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)
    except Exception:
        return name in insp.get_table_names()


def _create_items_if_missing() -> None:
    if _has_table("items"):
        return
    op.create_table(
        "items",
        sa.Column("id", sa.Integer, primary_key=True, nullable=False),
        sa.Column("sku", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        # 与模型字段对齐：给出最小必需列，避免后续 ORM 查询缺列
        sa.Column("qty_available", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def _create_warehouses_if_missing() -> None:
    if _has_table("warehouses"):
        return
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer, primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )


def _create_locations_if_missing() -> None:
    if _has_table("locations"):
        return
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("warehouse_id", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], name="fk_locations_warehouse", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("warehouse_id", "name", name="uq_locations_wh_name"),
    )


def upgrade() -> None:
    # 按依赖顺序创建（存在即跳过）
    _create_warehouses_if_missing()
    _create_locations_if_missing()
    _create_items_if_missing()


def downgrade() -> None:
    # 仅回滚 baseline 创建的三表（按依赖顺序）
    if _has_table("locations"):
        op.drop_table("locations")
    if _has_table("warehouses"):
        op.drop_table("warehouses")
    if _has_table("items"):
        op.drop_table("items")
