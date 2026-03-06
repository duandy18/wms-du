"""drop legacy zones and enforce pricing matrix unique

Revision ID: ff7ddf02de26
Revises: d60b9582ec9a
Create Date: 2026-03-06 23:39:44.589102

- drop legacy zone tables:
    shipping_provider_zone_brackets
    shipping_provider_zone_members
    shipping_provider_zones

- enforce unique index for pricing matrix:
    uq_sppm_group_min_max_coalesced
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ff7ddf02de26"
down_revision: Union[str, Sequence[str], None] = "d60b9582ec9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_ZONE_BRACKETS = "shipping_provider_zone_brackets"
LEGACY_ZONE_MEMBERS = "shipping_provider_zone_members"
LEGACY_ZONES = "shipping_provider_zones"

PRICING_MATRIX = "shipping_provider_pricing_matrix"
UQ_SPPM_GROUP_MIN_MAX = "uq_sppm_group_min_max_coalesced"


def _table_exists(insp: sa.Inspector, table_name: str) -> bool:
    return table_name in insp.get_table_names()


def _index_exists(insp: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(insp, table_name):
        return False
    return index_name in {idx["name"] for idx in insp.get_indexes(table_name)}


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _table_exists(insp, PRICING_MATRIX) and not _index_exists(insp, PRICING_MATRIX, UQ_SPPM_GROUP_MIN_MAX):
        op.create_index(
            UQ_SPPM_GROUP_MIN_MAX,
            PRICING_MATRIX,
            ["group_id", "min_kg"],
            unique=True,
            postgresql_where=None,
            postgresql_include=None,
            postgresql_using="btree",
            postgresql_ops=None,
        )
        op.drop_index(UQ_SPPM_GROUP_MIN_MAX, table_name=PRICING_MATRIX)
        op.execute(
            """
            CREATE UNIQUE INDEX uq_sppm_group_min_max_coalesced
            ON shipping_provider_pricing_matrix
            (group_id, min_kg, COALESCE(max_kg, 999999.000))
            """
        )

    if _table_exists(insp, LEGACY_ZONE_BRACKETS):
        op.drop_table(LEGACY_ZONE_BRACKETS)

    if _table_exists(insp, LEGACY_ZONE_MEMBERS):
        op.drop_table(LEGACY_ZONE_MEMBERS)

    if _table_exists(insp, LEGACY_ZONES):
        op.drop_table(LEGACY_ZONES)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _table_exists(insp, LEGACY_ZONES):
        op.create_table(
            LEGACY_ZONES,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scheme_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["scheme_id"],
                ["shipping_provider_pricing_schemes.id"],
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("scheme_id", "name", name="uq_sp_zones_scheme_name"),
        )

    if not _table_exists(insp, LEGACY_ZONE_MEMBERS):
        op.create_table(
            LEGACY_ZONE_MEMBERS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("zone_id", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(length=16), nullable=False),
            sa.Column("value", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["zone_id"],
                [f"{LEGACY_ZONES}.id"],
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("zone_id", "level", "value", name="uq_sp_zone_members_zone_level_value"),
        )

    if not _table_exists(insp, LEGACY_ZONE_BRACKETS):
        op.create_table(
            LEGACY_ZONE_BRACKETS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("zone_id", sa.Integer(), nullable=False),
            sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
            sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),
            sa.Column("pricing_mode", sa.String(length=32), nullable=False, server_default="flat"),
            sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True),
            sa.Column("base_kg", sa.Numeric(10, 3), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["zone_id"],
                [f"{LEGACY_ZONES}.id"],
                ondelete="RESTRICT",
            ),
        )

    insp = sa.inspect(bind)
    if _index_exists(insp, PRICING_MATRIX, UQ_SPPM_GROUP_MIN_MAX):
        op.drop_index(UQ_SPPM_GROUP_MIN_MAX, table_name=PRICING_MATRIX)
