"""add/ensure constraints & indexes on stocks (safe if table missing)

Revision ID: 20251006_add_constraints_to_stocks
Revises: f995a82ac74e
Create Date: 2025-10-06 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251006_add_constraints_to_stocks"
down_revision: Union[str, Sequence[str], None] = "f995a82ac74e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)  # 一些方言支持
    except Exception:
        return name in insp.get_table_names()


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def _unique_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {uc["name"] for uc in insp.get_unique_constraints(table)}
    except Exception:
        return set()


def upgrade() -> None:
    # 1) 若 stocks 不存在，先创建“最小可用”结构（PG/SQLite 通用）
    if not _has_table("stocks"):
        op.create_table(
            "stocks",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("location_id", sa.Integer(), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    # 2) 幂等补约束/索引
    uqs = _unique_names("stocks")
    idx = _index_names("stocks")

    if "uq_stocks_item_location" not in uqs:
        op.create_unique_constraint(
            "uq_stocks_item_location",
            "stocks",
            ["item_id", "location_id"],
        )

    if "ix_stocks_item" not in idx:
        op.create_index("ix_stocks_item", "stocks", ["item_id"], unique=False)

    if "ix_stocks_location" not in idx:
        op.create_index("ix_stocks_location", "stocks", ["location_id"], unique=False)

    # 热点联合索引（查询 item+location）
    if "ix_stock_item_loc" not in idx:
        op.create_index("ix_stock_item_loc", "stocks", ["item_id", "location_id"], unique=False)


def downgrade() -> None:
    # 只撤销本迁移创建的对象；不删除表结构
    idx = _index_names("stocks")
    uqs = _unique_names("stocks")

    if "ix_stock_item_loc" in idx:
        op.drop_index("ix_stock_item_loc", table_name="stocks")

    if "ix_stocks_location" in idx:
        op.drop_index("ix_stocks_location", table_name="stocks")

    if "ix_stocks_item" in idx:
        op.drop_index("ix_stocks_item", table_name="stocks")

    if "uq_stocks_item_location" in uqs:
        op.drop_constraint("uq_stocks_item_location", "stocks", type_="unique")
