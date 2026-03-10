"""remove pricing modules flatten scheme pricing

Revision ID: 49bacdd7e9b7
Revises: 33c405a7eecd
Create Date: 2026-03-10 08:07:03.005075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "49bacdd7e9b7"
down_revision: Union[str, Sequence[str], None] = "33c405a7eecd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ALLOWED_MODES_SQL = "('flat','linear_total','step_over','manual_quote')"


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1) ranges：新增 scheme_id / default_pricing_mode
    # ---------------------------------------------------------
    op.add_column(
        "shipping_provider_pricing_scheme_module_ranges",
        sa.Column("scheme_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shipping_provider_pricing_scheme_module_ranges",
        sa.Column(
            "default_pricing_mode",
            sa.String(length=32),
            nullable=False,
            server_default="flat",
        ),
    )

    op.create_foreign_key(
        "fk_sppsmr_scheme_id",
        "shipping_provider_pricing_scheme_module_ranges",
        "shipping_provider_pricing_schemes",
        ["scheme_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_shipping_provider_pricing_scheme_module_ranges_scheme_id",
        "shipping_provider_pricing_scheme_module_ranges",
        ["scheme_id"],
        unique=False,
    )

    # 通过旧 modules 关系回填 scheme_id
    op.execute(
        """
        UPDATE shipping_provider_pricing_scheme_module_ranges r
           SET scheme_id = m.scheme_id
          FROM shipping_provider_pricing_scheme_modules m
         WHERE r.module_id = m.id
        """
    )

    # 用现有 matrix 的主模式回填 default_pricing_mode；
    # 没有 cell 的 range 默认 flat
    op.execute(
        f"""
        WITH mode_counts AS (
            SELECT
                pm.module_range_id,
                pm.pricing_mode,
                COUNT(*) AS cnt
            FROM shipping_provider_pricing_matrix pm
            GROUP BY pm.module_range_id, pm.pricing_mode
        ),
        ranked AS (
            SELECT
                module_range_id,
                pricing_mode,
                ROW_NUMBER() OVER (
                    PARTITION BY module_range_id
                    ORDER BY cnt DESC, pricing_mode ASC
                ) AS rn
            FROM mode_counts
        )
        UPDATE shipping_provider_pricing_scheme_module_ranges r
           SET default_pricing_mode = ranked.pricing_mode
          FROM ranked
         WHERE ranked.module_range_id = r.id
           AND ranked.rn = 1
        """
    )

    op.alter_column(
        "shipping_provider_pricing_scheme_module_ranges",
        "scheme_id",
        nullable=False,
    )

    op.create_check_constraint(
        "ck_sppsmr_default_mode_valid",
        "shipping_provider_pricing_scheme_module_ranges",
        f"default_pricing_mode in {_ALLOWED_MODES_SQL}",
    )

    # 删旧 unique / index
    op.drop_constraint(
        "uq_sppsmr_module_sort_order",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="unique",
    )
    op.drop_constraint(
        "uq_sppsmr_module_range",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="unique",
    )
    op.drop_index(
        "uq_sppsmr_module_open_ended",
        table_name="shipping_provider_pricing_scheme_module_ranges",
    )

    # 建新 unique / index
    op.create_unique_constraint(
        "uq_sppsmr_scheme_sort_order",
        "shipping_provider_pricing_scheme_module_ranges",
        ["scheme_id", "sort_order"],
    )
    op.create_unique_constraint(
        "uq_sppsmr_scheme_range",
        "shipping_provider_pricing_scheme_module_ranges",
        ["scheme_id", "min_kg", "max_kg"],
    )
    op.create_index(
        "uq_sppsmr_scheme_open_ended",
        "shipping_provider_pricing_scheme_module_ranges",
        ["scheme_id", "min_kg"],
        unique=True,
        postgresql_where=sa.text("max_kg IS NULL"),
    )

    # ---------------------------------------------------------
    # 2) groups：先改唯一约束
    # ---------------------------------------------------------
    op.drop_constraint(
        "uq_sp_dest_groups_module_sort_order",
        "shipping_provider_destination_groups",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_sp_dest_groups_scheme_sort_order",
        "shipping_provider_destination_groups",
        ["scheme_id", "sort_order"],
    )

    # ---------------------------------------------------------
    # 3) matrix：删除 same-module FK + range_module_id
    # ---------------------------------------------------------
    op.drop_constraint(
        "fk_sppm_group_same_module",
        "shipping_provider_pricing_matrix",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_sppm_range_same_module",
        "shipping_provider_pricing_matrix",
        type_="foreignkey",
    )
    op.drop_column("shipping_provider_pricing_matrix", "range_module_id")

    # ---------------------------------------------------------
    # 4) 删 ranges/groups 对 modules 的 FK，再删 module_id
    # ---------------------------------------------------------
    op.drop_constraint(
        "fk_sppsmr_module_id",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_dest_group_module",
        "shipping_provider_destination_groups",
        type_="foreignkey",
    )

    op.drop_column("shipping_provider_pricing_scheme_module_ranges", "module_id")
    op.drop_column("shipping_provider_destination_groups", "module_id")

    # ---------------------------------------------------------
    # 5) 删除 modules 表
    # ---------------------------------------------------------
    op.drop_table("shipping_provider_pricing_scheme_modules")

    # 去掉默认值常量，避免以后 DB 端偷偷兜底
    op.alter_column(
        "shipping_provider_pricing_scheme_module_ranges",
        "default_pricing_mode",
        server_default=None,
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # 1) 重建 modules 表
    # ---------------------------------------------------------
    op.create_table(
        "shipping_provider_pricing_scheme_modules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("module_code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sppsm_scheme_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "module_code in ('standard','other')",
            name="ck_sppsm_module_code_valid",
        ),
        sa.UniqueConstraint(
            "scheme_id",
            "module_code",
            name="uq_sppsm_scheme_module_code",
        ),
        sa.UniqueConstraint(
            "scheme_id",
            "sort_order",
            name="uq_sppsm_scheme_sort_order",
        ),
    )

    # 为每个 scheme 重建两条 module 记录
    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_modules (
            scheme_id, module_code, name, sort_order
        )
        SELECT id, 'standard', '标准区域', 0
          FROM shipping_provider_pricing_schemes
        """
    )
    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_modules (
            scheme_id, module_code, name, sort_order
        )
        SELECT id, 'other', '其他区域', 1
          FROM shipping_provider_pricing_schemes
        """
    )

    # ---------------------------------------------------------
    # 2) groups：补回 module_id（全部挂回 standard）
    # ---------------------------------------------------------
    op.add_column(
        "shipping_provider_destination_groups",
        sa.Column("module_id", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE shipping_provider_destination_groups g
           SET module_id = m.id
          FROM shipping_provider_pricing_scheme_modules m
         WHERE g.scheme_id = m.scheme_id
           AND m.module_code = 'standard'
        """
    )

    op.alter_column(
        "shipping_provider_destination_groups",
        "module_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_dest_group_module",
        "shipping_provider_destination_groups",
        "shipping_provider_pricing_scheme_modules",
        ["module_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "uq_sp_dest_groups_scheme_sort_order",
        "shipping_provider_destination_groups",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_sp_dest_groups_module_sort_order",
        "shipping_provider_destination_groups",
        ["module_id", "sort_order"],
    )

    # ---------------------------------------------------------
    # 3) ranges：补回 module_id，删 scheme_id/default_pricing_mode
    # ---------------------------------------------------------
    op.add_column(
        "shipping_provider_pricing_scheme_module_ranges",
        sa.Column("module_id", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE shipping_provider_pricing_scheme_module_ranges r
           SET module_id = m.id
          FROM shipping_provider_pricing_scheme_modules m
         WHERE r.scheme_id = m.scheme_id
           AND m.module_code = 'standard'
        """
    )

    op.alter_column(
        "shipping_provider_pricing_scheme_module_ranges",
        "module_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_sppsmr_module_id",
        "shipping_provider_pricing_scheme_module_ranges",
        "shipping_provider_pricing_scheme_modules",
        ["module_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "uq_sppsmr_scheme_sort_order",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="unique",
    )
    op.drop_constraint(
        "uq_sppsmr_scheme_range",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="unique",
    )
    op.drop_index(
        "uq_sppsmr_scheme_open_ended",
        table_name="shipping_provider_pricing_scheme_module_ranges",
    )
    op.drop_constraint(
        "ck_sppsmr_default_mode_valid",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="check",
    )
    op.drop_index(
        "ix_shipping_provider_pricing_scheme_module_ranges_scheme_id",
        table_name="shipping_provider_pricing_scheme_module_ranges",
    )

    op.create_unique_constraint(
        "uq_sppsmr_module_sort_order",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_id", "sort_order"],
    )
    op.create_unique_constraint(
        "uq_sppsmr_module_range",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_id", "min_kg", "max_kg"],
    )
    op.create_index(
        "uq_sppsmr_module_open_ended",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_id", "min_kg"],
        unique=True,
        postgresql_where=sa.text("max_kg IS NULL"),
    )

    # ---------------------------------------------------------
    # 4) matrix：补回 range_module_id 和 same-module FK
    # ---------------------------------------------------------
    op.add_column(
        "shipping_provider_pricing_matrix",
        sa.Column("range_module_id", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE shipping_provider_pricing_matrix pm
           SET range_module_id = r.module_id
          FROM shipping_provider_pricing_scheme_module_ranges r
         WHERE pm.module_range_id = r.id
        """
    )

    op.alter_column(
        "shipping_provider_pricing_matrix",
        "range_module_id",
        nullable=False,
    )

    op.create_foreign_key(
        "fk_sppm_group_same_module",
        "shipping_provider_pricing_matrix",
        "shipping_provider_destination_groups",
        ["group_id", "range_module_id"],
        ["id", "module_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_sppm_range_same_module",
        "shipping_provider_pricing_matrix",
        "shipping_provider_pricing_scheme_module_ranges",
        ["module_range_id", "range_module_id"],
        ["id", "module_id"],
        ondelete="CASCADE",
    )

    # ---------------------------------------------------------
    # 5) 删 ranges 上的新字段
    # ---------------------------------------------------------
    op.drop_index(
        "ix_shipping_provider_pricing_scheme_module_ranges_scheme_id",
        table_name="shipping_provider_pricing_scheme_module_ranges",
    )
    op.drop_constraint(
        "fk_sppsmr_scheme_id",
        "shipping_provider_pricing_scheme_module_ranges",
        type_="foreignkey",
    )
    op.drop_column("shipping_provider_pricing_scheme_module_ranges", "default_pricing_mode")
    op.drop_column("shipping_provider_pricing_scheme_module_ranges", "scheme_id")
