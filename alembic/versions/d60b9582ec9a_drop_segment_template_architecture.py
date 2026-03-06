"""drop segment template architecture

Revision ID: d60b9582ec9a
Revises: 29924e401ed0
Create Date: 2026-03-06 22:01:23.324979
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d60b9582ec9a"
down_revision: Union[str, Sequence[str], None] = "29924e401ed0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite(bind) -> bool:
    return (bind.dialect.name or "").lower() == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)
    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # ---------------------------------------------------------
    # 1. drop scheme.default_segment_template_id
    # ---------------------------------------------------------
    if "shipping_provider_pricing_schemes" in insp.get_table_names(schema=schema):
        cols = {c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)}
        idxs = {i["name"] for i in insp.get_indexes("shipping_provider_pricing_schemes", schema=schema)}
        fks = {fk["name"] for fk in insp.get_foreign_keys("shipping_provider_pricing_schemes", schema=schema) if fk.get("name")}

        if "default_segment_template_id" in cols:
            if "ix_sch_def_seg_tpl" in idxs:
                op.drop_index("ix_sch_def_seg_tpl", table_name="shipping_provider_pricing_schemes")

            if "fk_sch_def_seg_tpl" in fks:
                op.drop_constraint(
                    "fk_sch_def_seg_tpl",
                    "shipping_provider_pricing_schemes",
                    type_="foreignkey",
                )

            with op.batch_alter_table("shipping_provider_pricing_schemes") as batch_op:
                batch_op.drop_column("default_segment_template_id")

    # ---------------------------------------------------------
    # 2. drop zones.segment_template_id
    # ---------------------------------------------------------
    if "shipping_provider_zones" in insp.get_table_names(schema=schema):
        cols = {c["name"] for c in insp.get_columns("shipping_provider_zones", schema=schema)}
        idxs = {i["name"] for i in insp.get_indexes("shipping_provider_zones", schema=schema)}
        fks = {fk["name"] for fk in insp.get_foreign_keys("shipping_provider_zones", schema=schema) if fk.get("name")}

        if "segment_template_id" in cols:
            if "ix_sp_zones_segment_template_id" in idxs:
                op.drop_index("ix_sp_zones_segment_template_id", table_name="shipping_provider_zones")

            if "fk_sp_zones_segment_template_id" in fks:
                op.drop_constraint(
                    "fk_sp_zones_segment_template_id",
                    "shipping_provider_zones",
                    type_="foreignkey",
                )

            with op.batch_alter_table("shipping_provider_zones") as batch_op:
                batch_op.drop_column("segment_template_id")

    # refresh inspector
    insp = sa.inspect(bind)

    # ---------------------------------------------------------
    # 3. drop template_items table
    # ---------------------------------------------------------
    if "shipping_provider_pricing_scheme_segment_template_items" in insp.get_table_names(schema=schema):
        idxs = {i["name"] for i in insp.get_indexes("shipping_provider_pricing_scheme_segment_template_items", schema=schema)}

        if not sqlite:
            op.execute("DROP INDEX IF EXISTS uq_spssti_tpl_min_max")

        if "ix_spssti_tpl_ord" in idxs:
            op.drop_index(
                "ix_spssti_tpl_ord",
                table_name="shipping_provider_pricing_scheme_segment_template_items",
            )

        op.drop_table("shipping_provider_pricing_scheme_segment_template_items")

    # ---------------------------------------------------------
    # 4. drop templates table
    # ---------------------------------------------------------
    if "shipping_provider_pricing_scheme_segment_templates" in insp.get_table_names(schema=schema):
        idxs = {i["name"] for i in insp.get_indexes("shipping_provider_pricing_scheme_segment_templates", schema=schema)}

        if "ix_spsst_scheme_active" in idxs:
            op.drop_index(
                "ix_spsst_scheme_active",
                table_name="shipping_provider_pricing_scheme_segment_templates",
            )

        op.drop_table("shipping_provider_pricing_scheme_segment_templates")


def downgrade() -> None:
    bind = op.get_bind()
    sqlite = _is_sqlite(bind)
    insp = sa.inspect(bind)
    schema = None if sqlite else "public"

    # ---------------------------------------------------------
    # recreate templates table
    # ---------------------------------------------------------
    if "shipping_provider_pricing_scheme_segment_templates" not in insp.get_table_names(schema=schema):
        op.create_table(
            "shipping_provider_pricing_scheme_segment_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scheme_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["scheme_id"], ["shipping_provider_pricing_schemes.id"], ondelete="CASCADE"),
        )

        op.create_index(
            "ix_spsst_scheme_active",
            "shipping_provider_pricing_scheme_segment_templates",
            ["scheme_id", "is_active"],
            unique=False,
        )

    # ---------------------------------------------------------
    # recreate template_items table
    # ---------------------------------------------------------
    insp = sa.inspect(bind)
    if "shipping_provider_pricing_scheme_segment_template_items" not in insp.get_table_names(schema=schema):
        op.create_table(
            "shipping_provider_pricing_scheme_segment_template_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("ord", sa.Integer(), nullable=False),
            sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
            sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["template_id"], ["shipping_provider_pricing_scheme_segment_templates.id"], ondelete="CASCADE"),
        )

        op.create_index(
            "ix_spssti_tpl_ord",
            "shipping_provider_pricing_scheme_segment_template_items",
            ["template_id", "ord"],
            unique=False,
        )

    # ---------------------------------------------------------
    # recreate columns
    # ---------------------------------------------------------
    insp = sa.inspect(bind)

    if "shipping_provider_pricing_schemes" in insp.get_table_names(schema=schema):
        cols = {c["name"] for c in insp.get_columns("shipping_provider_pricing_schemes", schema=schema)}
        if "default_segment_template_id" not in cols:
            with op.batch_alter_table("shipping_provider_pricing_schemes") as batch_op:
                batch_op.add_column(sa.Column("default_segment_template_id", sa.Integer(), nullable=True))

            op.create_foreign_key(
                "fk_sch_def_seg_tpl",
                "shipping_provider_pricing_schemes",
                "shipping_provider_pricing_scheme_segment_templates",
                ["default_segment_template_id"],
                ["id"],
                ondelete="SET NULL",
            )

            op.create_index(
                "ix_sch_def_seg_tpl",
                "shipping_provider_pricing_schemes",
                ["default_segment_template_id"],
                unique=False,
            )

    if "shipping_provider_zones" in insp.get_table_names(schema=schema):
        cols = {c["name"] for c in insp.get_columns("shipping_provider_zones", schema=schema)}
        if "segment_template_id" not in cols:
            with op.batch_alter_table("shipping_provider_zones") as batch_op:
                batch_op.add_column(sa.Column("segment_template_id", sa.Integer(), nullable=True))

            op.create_foreign_key(
                "fk_sp_zones_segment_template_id",
                "shipping_provider_zones",
                "shipping_provider_pricing_scheme_segment_templates",
                ["segment_template_id"],
                ["id"],
                ondelete="RESTRICT",
            )

            op.create_index(
                "ix_sp_zones_segment_template_id",
                "shipping_provider_zones",
                ["segment_template_id"],
                unique=False,
            )
