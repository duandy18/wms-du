"""SQLite-safe: add stock-location link

Revision ID: 1f2c758faee3
Revises: 1a189010e7b4
Create Date: 2025-10-06 10:38:09.593067
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2c758faee3"
down_revision: str | Sequence[str] | None = "1a189010e7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """SQLite-safe schema upgrade."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # ---- 防止重复执行 ----
    existing = [t.lower() for t in inspector.get_table_names()]

    # 1️⃣ warehouses
    if "warehouses" not in existing:
        op.create_table(
            "warehouses",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column("name", sa.String(), unique=True, index=True),
            sa.Column("address", sa.String()),
        )

    # 2️⃣ locations
    if "locations" not in existing:
        op.create_table(
            "locations",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.id")),
        )

    # 3️⃣ stocks
    if "stocks" not in existing:
        op.create_table(
            "stocks",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
            sa.Column("location_id", sa.String(), sa.ForeignKey("locations.id")),
            sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        )

    print("✅ SQLite-safe migration applied (warehouses, locations, stocks checked).")


def downgrade() -> None:
    """SQLite-safe downgrade."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = [t.lower() for t in inspector.get_table_names()]

    for tbl in ["stocks", "locations", "warehouses"]:
        if tbl in existing:
            op.drop_table(tbl)

    print("⚠️ SQLite-safe downgrade executed (tables dropped if existed).")
