"""add warehouses and locations (safe-create with existence checks)

Revision ID: 3b_add_warehouses_locations
Revises: 7f_merge_cycle_fix
Create Date: 2025-10-12 20:21:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3b_add_warehouses_locations"
down_revision = "1223487447f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(name)
    except Exception:
        return name in insp.get_table_names()


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {ix["name"] for ix in insp.get_indexes(table)}
    except Exception:
        return set()


def _fk_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return {fk["name"] for fk in insp.get_foreign_keys(table) if fk.get("name")}
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
    # --- warehouses ---
    if not _has_table("warehouses"):
        op.create_table(
            "warehouses",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        )

    # --- locations ---
    if not _has_table("locations"):
        op.create_table(
            "locations",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["warehouse_id"], ["warehouses.id"],
                name="fk_locations_warehouse", ondelete="RESTRICT",
            ),
        )

    # 约束/索引（缺则建）
    uqs = _unique_names("locations")
    if "uq_locations_wh_name" not in uqs:
        op.create_unique_constraint("uq_locations_wh_name", "locations", ["warehouse_id", "name"])

    idx = _index_names("locations")
    if "ix_locations_warehouse" not in idx:
        op.create_index("ix_locations_warehouse", "locations", ["warehouse_id"], unique=False)
    if "ix_locations_name" not in idx:
        op.create_index("ix_locations_name", "locations", ["name"], unique=False)


def downgrade() -> None:
    # 先删从表，再删主表
    if _has_table("locations"):
        idx = _index_names("locations")
        if "ix_locations_name" in idx:
            op.drop_index("ix_locations_name", table_name="locations")
        if "ix_locations_warehouse" in idx:
            op.drop_index("ix_locations_warehouse", table_name="locations")

        fks = _fk_names("locations")
        if "fk_locations_warehouse" in fks:
            op.drop_constraint("fk_locations_warehouse", "locations", type_="foreignkey")

        uqs = _unique_names("locations")
        if "uq_locations_wh_name" in uqs:
            op.drop_constraint("uq_locations_wh_name", "locations", type_="unique")

        op.drop_table("locations")

    if _has_table("warehouses"):
        op.drop_table("warehouses")
