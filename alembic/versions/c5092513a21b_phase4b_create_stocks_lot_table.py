"""phase4b create stocks_lot table

Revision ID: c5092513a21b
Revises: 08a02787b988
Create Date: 2026-02-25 11:27:10.603292

目标：
- 新建 stocks_lot：以 lot 为主维度的库存余额投影表（ledger 可 rebuild）
- 允许 lot_id 为 NULL（“无 lot”槽位），用生成列 lot_id_key=coalesce(lot_id,0) 参与唯一性
- 不修改现有 stocks（双轨运行前置）
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5092513a21b"
down_revision: Union[str, Sequence[str], None] = "08a02787b988"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) create table
    op.create_table(
        "stocks_lot",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        # 迁移期给默认 0 更安全；随后立刻 drop default（对齐 stocks 的“事实列无默认”气质）
        sa.Column("qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "lot_id_key",
            sa.Integer(),
            sa.Computed("coalesce(lot_id, 0)", persisted=True),
            nullable=False,
        ),
    )

    # 2) foreign keys（命名风格对齐：fk_<table>_<col or role>）
    op.create_foreign_key(
        "fk_stocks_lot_item",
        "stocks_lot",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_stocks_lot_warehouse",
        "stocks_lot",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # lot 是主维度：对齐 lots 被引用语义（ledger / inbound_receipt_lines 都是 RESTRICT）
    op.create_foreign_key(
        "fk_stocks_lot_lot_id",
        "stocks_lot",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 3) indexes（对齐 ix_* 命名）
    op.create_index("ix_stocks_lot_lot_id_key", "stocks_lot", ["lot_id_key"], unique=False)
    op.create_index("ix_stocks_lot_item_id", "stocks_lot", ["item_id"], unique=False)
    op.create_index("ix_stocks_lot_warehouse_id", "stocks_lot", ["warehouse_id"], unique=False)
    op.create_index(
        "ix_stocks_lot_item_wh_lot",
        "stocks_lot",
        ["item_id", "warehouse_id", "lot_id"],
        unique=False,
    )

    # 4) unique constraint（稳定名字，为后续 ON CONFLICT(constraint=...) 预留）
    op.create_unique_constraint(
        "uq_stocks_lot_item_wh_lot",
        "stocks_lot",
        ["item_id", "warehouse_id", "lot_id_key"],
    )

    # 5) check constraint（护栏 + 自解释）
    op.create_check_constraint(
        "ck_stocks_lot_lot_id_key_consistent",
        "stocks_lot",
        "lot_id_key = coalesce(lot_id, 0)",
    )

    # 6) drop default（对齐 stocks：事实余额列通常不长期保留 default）
    op.alter_column("stocks_lot", "qty", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_stocks_lot_lot_id_key_consistent", "stocks_lot", type_="check")
    op.drop_constraint("uq_stocks_lot_item_wh_lot", "stocks_lot", type_="unique")

    op.drop_index("ix_stocks_lot_item_wh_lot", table_name="stocks_lot")
    op.drop_index("ix_stocks_lot_warehouse_id", table_name="stocks_lot")
    op.drop_index("ix_stocks_lot_item_id", table_name="stocks_lot")
    op.drop_index("ix_stocks_lot_lot_id_key", table_name="stocks_lot")

    op.drop_constraint("fk_stocks_lot_lot_id", "stocks_lot", type_="foreignkey")
    op.drop_constraint("fk_stocks_lot_warehouse", "stocks_lot", type_="foreignkey")
    op.drop_constraint("fk_stocks_lot_item", "stocks_lot", type_="foreignkey")

    op.drop_table("stocks_lot")
