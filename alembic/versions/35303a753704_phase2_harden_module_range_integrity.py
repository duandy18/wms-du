"""phase2_harden_module_range_integrity

Revision ID: 35303a753704
Revises: c13667fd5d0f
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "35303a753704"
down_revision: Union[str, Sequence[str], None] = "c13667fd5d0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(conn, table_name: str) -> set[str]:
    insp = inspect(conn)
    return {c["name"] for c in insp.get_columns(table_name)}


def _table_indexes(conn, table_name: str) -> set[str]:
    insp = inspect(conn)
    return {i["name"] for i in insp.get_indexes(table_name)}


def _table_unique_constraints(conn, table_name: str) -> set[str]:
    insp = inspect(conn)
    return {u["name"] for u in insp.get_unique_constraints(table_name)}


def _table_foreign_keys(conn, table_name: str) -> set[str]:
    insp = inspect(conn)
    return {fk["name"] for fk in insp.get_foreign_keys(table_name)}


def upgrade() -> None:
    conn = op.get_bind()

    ranges_uniques = _table_unique_constraints(conn, "shipping_provider_pricing_scheme_module_ranges")
    ranges_indexes = _table_indexes(conn, "shipping_provider_pricing_scheme_module_ranges")
    group_uniques = _table_unique_constraints(conn, "shipping_provider_destination_groups")
    matrix_columns = _table_columns(conn, "shipping_provider_pricing_matrix")
    matrix_fks = _table_foreign_keys(conn, "shipping_provider_pricing_matrix")

    # --------------------------------------------------
    # 1) module_ranges：补复合唯一键（供复合外键引用）
    # --------------------------------------------------
    if "uq_sppsmr_id_module" not in ranges_uniques:
        op.create_unique_constraint(
            "uq_sppsmr_id_module",
            "shipping_provider_pricing_scheme_module_ranges",
            ["id", "module_id"],
        )

    # --------------------------------------------------
    # 2) module_ranges：防止 open-ended range 重复
    # --------------------------------------------------
    if "uq_sppsmr_module_open_ended" not in ranges_indexes:
        op.create_index(
            "uq_sppsmr_module_open_ended",
            "shipping_provider_pricing_scheme_module_ranges",
            ["module_id", "min_kg"],
            unique=True,
            postgresql_where=sa.text("max_kg IS NULL"),
        )

    # --------------------------------------------------
    # 3) destination_groups：补复合唯一键（供复合外键引用）
    # --------------------------------------------------
    if "uq_spdg_id_module" not in group_uniques:
        op.create_unique_constraint(
            "uq_spdg_id_module",
            "shipping_provider_destination_groups",
            ["id", "module_id"],
        )

    # --------------------------------------------------
    # 4) pricing_matrix：增加 range_module_id
    # --------------------------------------------------
    if "range_module_id" not in matrix_columns:
        with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
            batch_op.add_column(sa.Column("range_module_id", sa.Integer(), nullable=True))

        op.execute(
            """
            UPDATE shipping_provider_pricing_matrix pm
               SET range_module_id = r.module_id
              FROM shipping_provider_pricing_scheme_module_ranges r
             WHERE pm.module_range_id = r.id
            """
        )

        with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
            batch_op.alter_column(
                "range_module_id",
                existing_type=sa.Integer(),
                nullable=False,
            )

    # refresh metadata after possible column add
    matrix_fks = _table_foreign_keys(conn, "shipping_provider_pricing_matrix")

    # --------------------------------------------------
    # 5) group 与 range 必须属于同一 module
    # --------------------------------------------------
    if "fk_sppm_group_same_module" not in matrix_fks:
        op.create_foreign_key(
            "fk_sppm_group_same_module",
            "shipping_provider_pricing_matrix",
            "shipping_provider_destination_groups",
            ["group_id", "range_module_id"],
            ["id", "module_id"],
            ondelete="CASCADE",
        )

    # --------------------------------------------------
    # 6) module_range_id 与 module_id 必须一致
    # --------------------------------------------------
    if "fk_sppm_range_same_module" not in matrix_fks:
        op.create_foreign_key(
            "fk_sppm_range_same_module",
            "shipping_provider_pricing_matrix",
            "shipping_provider_pricing_scheme_module_ranges",
            ["module_range_id", "range_module_id"],
            ["id", "module_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    conn = op.get_bind()

    matrix_columns = _table_columns(conn, "shipping_provider_pricing_matrix")
    matrix_fks = _table_foreign_keys(conn, "shipping_provider_pricing_matrix")
    group_uniques = _table_unique_constraints(conn, "shipping_provider_destination_groups")
    ranges_uniques = _table_unique_constraints(conn, "shipping_provider_pricing_scheme_module_ranges")
    ranges_indexes = _table_indexes(conn, "shipping_provider_pricing_scheme_module_ranges")

    if "fk_sppm_range_same_module" in matrix_fks:
        op.drop_constraint(
            "fk_sppm_range_same_module",
            "shipping_provider_pricing_matrix",
            type_="foreignkey",
        )

    if "fk_sppm_group_same_module" in matrix_fks:
        op.drop_constraint(
            "fk_sppm_group_same_module",
            "shipping_provider_pricing_matrix",
            type_="foreignkey",
        )

    if "range_module_id" in matrix_columns:
        with op.batch_alter_table("shipping_provider_pricing_matrix") as batch_op:
            batch_op.drop_column("range_module_id")

    if "uq_spdg_id_module" in group_uniques:
        op.drop_constraint(
            "uq_spdg_id_module",
            "shipping_provider_destination_groups",
            type_="unique",
        )

    if "uq_sppsmr_module_open_ended" in ranges_indexes:
        op.drop_index(
            "uq_sppsmr_module_open_ended",
            table_name="shipping_provider_pricing_scheme_module_ranges",
        )

    if "uq_sppsmr_id_module" in ranges_uniques:
        op.drop_constraint(
            "uq_sppsmr_id_module",
            "shipping_provider_pricing_scheme_module_ranges",
            type_="unique",
        )
