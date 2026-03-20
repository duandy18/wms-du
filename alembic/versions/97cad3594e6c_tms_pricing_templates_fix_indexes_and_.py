"""tms_pricing_templates_fix_indexes_and_constraints

Revision ID: 97cad3594e6c
Revises: 02a284d9351c
Create Date: 2026-03-20 13:29:35.143663
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "97cad3594e6c"
down_revision: Union[str, Sequence[str], None] = "02a284d9351c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


T_RANGES = "shipping_provider_pricing_template_module_ranges"
T_GROUPS = "shipping_provider_pricing_template_destination_groups"
T_MEMBERS = "shipping_provider_pricing_template_destination_group_members"
T_MATRIX = "shipping_provider_pricing_template_matrix"


def _table_exists(insp: sa.Inspector, table_name: str) -> bool:
    return table_name in insp.get_table_names()


def _index_exists(insp: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(insp, table_name):
        return False
    return index_name in {idx["name"] for idx in insp.get_indexes(table_name)}


def _unique_exists(insp: sa.Inspector, table_name: str, name: str) -> bool:
    if not _table_exists(insp, table_name):
        return False
    return name in {c["name"] for c in insp.get_unique_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _table_exists(insp, T_RANGES):
        if not _index_exists(insp, T_RANGES, "ix_spptmr_template_id"):
            op.create_index("ix_spptmr_template_id", T_RANGES, ["template_id"], unique=False)
        if not _unique_exists(insp, T_RANGES, "uq_spptmr_template_sort_order"):
            op.create_unique_constraint(
                "uq_spptmr_template_sort_order",
                T_RANGES,
                ["template_id", "sort_order"],
            )

    if _table_exists(insp, T_GROUPS):
        if not _index_exists(insp, T_GROUPS, "ix_spptdg_template_id"):
            op.create_index("ix_spptdg_template_id", T_GROUPS, ["template_id"], unique=False)
        if not _unique_exists(insp, T_GROUPS, "uq_spptdg_template_sort_order"):
            op.create_unique_constraint(
                "uq_spptdg_template_sort_order",
                T_GROUPS,
                ["template_id", "sort_order"],
            )

    if _table_exists(insp, T_MATRIX):
        if not _index_exists(insp, T_MATRIX, "ix_spptm_group_id"):
            op.create_index("ix_spptm_group_id", T_MATRIX, ["group_id"], unique=False)
        if not _unique_exists(insp, T_MATRIX, "uq_spptm_group_module_range"):
            op.create_unique_constraint(
                "uq_spptm_group_module_range",
                T_MATRIX,
                ["group_id", "module_range_id"],
            )

    if _table_exists(insp, T_MEMBERS):
        if not _index_exists(insp, T_MEMBERS, "ix_spptdgm_group_province"):
            op.create_index(
                "ix_spptdgm_group_province",
                T_MEMBERS,
                ["group_id", "province_code", "province_name"],
                unique=False,
            )

        if not _index_exists(insp, T_MEMBERS, "uq_spptdgm_group_province_key"):
            op.execute(
                """
                CREATE UNIQUE INDEX uq_spptdgm_group_province_key
                ON shipping_provider_pricing_template_destination_group_members
                (group_id, COALESCE(province_code, ''), COALESCE(province_name, ''))
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _index_exists(insp, T_MEMBERS, "uq_spptdgm_group_province_key"):
        op.execute(text("DROP INDEX uq_spptdgm_group_province_key"))

    if _index_exists(insp, T_MEMBERS, "ix_spptdgm_group_province"):
        op.drop_index("ix_spptdgm_group_province", table_name=T_MEMBERS)

    if _index_exists(insp, T_MATRIX, "ix_spptm_group_id"):
        op.drop_index("ix_spptm_group_id", table_name=T_MATRIX)

    if _index_exists(insp, T_GROUPS, "ix_spptdg_template_id"):
        op.drop_index("ix_spptdg_template_id", table_name=T_GROUPS)

    if _index_exists(insp, T_RANGES, "ix_spptmr_template_id"):
        op.drop_index("ix_spptmr_template_id", table_name=T_RANGES)
