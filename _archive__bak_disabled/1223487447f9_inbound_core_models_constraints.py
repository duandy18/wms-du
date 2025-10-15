"""inbound core models + constraints

Revision ID: 1223487447f9
Revises: 1f9e5c2b8a11
Create Date: 2025-10-12 11:25:39.520735
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1223487447f9"
down_revision = "2a01baddb002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {ix["name"] for ix in insp.get_indexes(table_name)}


def _unique_constraints(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {uc["name"] for uc in insp.get_unique_constraints(table_name)}


def upgrade() -> None:
    # ----- batches -----
    if {"item_id", "code"}.issubset(_table_columns("batches")):
        uqs = _unique_constraints("batches")
        if "uq_batch_item_code" not in uqs:
            op.create_unique_constraint("uq_batch_item_code", "batches", ["item_id", "code"])

    if "expiry_date" in _table_columns("batches"):
        idx = _index_names("batches")
        if "ix_batches_expiry" not in idx:
            op.create_index("ix_batches_expiry", "batches", ["expiry_date"], unique=False)

    # ----- stocks -----
    stock_cols = _table_columns("stocks")
    stock_uqs = _unique_constraints("stocks")
    stock_idx = _index_names("stocks")

    # 根据是否存在 batch_id 决定唯一约束的列
    if {"item_id", "location_id"}.issubset(stock_cols):
        if "batch_id" in stock_cols:
            if "uq_stock_item_loc_batch" not in stock_uqs:
                op.create_unique_constraint(
                    "uq_stock_item_loc_batch",
                    "stocks",
                    ["item_id", "location_id", "batch_id"],
                )
        # 无 batch_id 的场景：唯一约束为 (item_id, location_id)
        elif "uq_stocks_item_location" not in stock_uqs:
            op.create_unique_constraint(
                "uq_stocks_item_location",
                "stocks",
                ["item_id", "location_id"],
            )

        # 热点联合索引 (item_id, location_id)
        if "ix_stock_item_loc" not in stock_idx:
            op.create_index(
                "ix_stock_item_loc",
                "stocks",
                ["item_id", "location_id"],
                unique=False,
            )

    # ----- stock_ledger -----
    ledger_cols = _table_columns("stock_ledger")
    ledger_idx = _index_names("stock_ledger")

    # (item_id, ts) 检索
    if {"item_id", "ts"}.issubset(ledger_cols):
        if "ix_ledger_item_ts" not in ledger_idx:
            op.create_index("ix_ledger_item_ts", "stock_ledger", ["item_id", "ts"], unique=False)

    # (ref, ref_line) 幂等唯一
    if {"ref", "ref_line"}.issubset(ledger_cols):
        if "ix_ledger_ref" not in ledger_idx:
            op.create_index("ix_ledger_ref", "stock_ledger", ["ref", "ref_line"], unique=True)


def downgrade() -> None:
    # stock_ledger
    if "ix_ledger_ref" in _index_names("stock_ledger"):
        op.drop_index("ix_ledger_ref", table_name="stock_ledger")
    if "ix_ledger_item_ts" in _index_names("stock_ledger"):
        op.drop_index("ix_ledger_item_ts", table_name="stock_ledger")

    # stocks
    uqs = _unique_constraints("stocks")
    if "uq_stock_item_loc_batch" in uqs:
        op.drop_constraint("uq_stock_item_loc_batch", "stocks", type_="unique")
    if "uq_stocks_item_location" in uqs:
        op.drop_constraint("uq_stocks_item_location", "stocks", type_="unique")
    if "ix_stock_item_loc" in _index_names("stocks"):
        op.drop_index("ix_stock_item_loc", table_name="stocks")

    # batches
    if "ix_batches_expiry" in _index_names("batches"):
        op.drop_index("ix_batches_expiry", table_name="batches")
    if "uq_batch_item_code" in _unique_constraints("batches"):
        op.drop_constraint("uq_batch_item_code", "batches", type_="unique")
